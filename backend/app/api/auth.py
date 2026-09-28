"""认证 API：登录、查询当前用户、首次初始化设置、改密"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.auth import (
    AUTH_COOKIE_NAME,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db import get_session
from app.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=72)


class SetupBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=8, max_length=72)


def _set_cookie(response: Response, token: str) -> None:
    """写 HttpOnly cookie。前端通过同源也能拿到。"""
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=60 * 60 * 24,
        httponly=True,
        samesite="lax",
        secure=False,  # NAS 内网通常 http，前端在 Settings 页面可改；这里保守 False
        path="/",
    )


@router.post("/login")
def login(body: LoginBody, response: Response, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.username == body.username)).first()
    if user is None or not user.enabled:
        logger.info("login fail: user不存在或停用 username=%s", body.username)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(body.password, user.password_hash):
        logger.info("login fail: 密码错 username=%s", body.username)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user)
    _set_cookie(response, token)
    return {
        "token": token,
        "must_change_password": user.must_change_password,
        "user": {"id": user.id, "username": user.username, "role": user.role},
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "must_change_password": user.must_change_password,
    }


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码错误")
    session.add(User.__class__)  # noop 占位避免 unused
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    session.add(user)
    session.commit()
    return {"ok": True}


@router.get("/initialized")
def initialized(session: Session = Depends(get_session)):
    """探测：系统是否已经设置过密码？给登录页判断是否走 /setup 流程。"""
    user = session.exec(select(User).where(User.username == "admin")).first()
    initialized = bool(user and not user.password_hash.startswith("!UNINITIALIZED!"))
    return {"initialized": initialized}


@router.post("/setup")
def setup(body: SetupBody, session: Session = Depends(get_session)):
    """无 token 的本地初始化入口（只有当 admin 还是 !UNINITIALIZED! 时才允许）。
    Docker 模式不要走这里——entrypoint.sh 直接写入；这里用于本地开发没人手设密码。
    """
    user = session.exec(select(User).where(User.username == "admin")).first()
    if user and not user.password_hash.startswith("!UNINITIALIZED!"):
        raise HTTPException(status_code=400, detail="系统已初始化，请走 /login")
    if user is None:
        user = User(
            username=body.username,
            password_hash=hash_password(body.password),
            role="admin",
            must_change_password=False,
            enabled=True,
        )
        session.add(user)
    else:
        user.username = body.username
        user.password_hash = hash_password(body.password)
        user.must_change_password = False
    session.commit()
    logger.info("本地初始化完成：username=%s", body.username)
    return {"ok": True}


def generate_strong_password(length: int = 14) -> str:
    """生成 entrypoint 用的密码。带前后缀避免歧义字符。"""
    # 14 位：3 段用 - 分隔，每段 4 字符，从去除易混字符的字母表选
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
    alphabet += "!@#$%^&*"
    parts = []
    for _ in range(3):
        chunk = "".join(secrets.choice(alphabet) for _ in range(length // 3))
        parts.append(chunk)
    return "-".join(parts)
