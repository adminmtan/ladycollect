"""认证 API：登录、查询当前用户、首次初始化设置、改密"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from typing import Annotated
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


class DevResetBody(BaseModel):
    """开发模式专用：把 admin 密码重置为已知值，避免本地忘了密码后无法登录。
    启用条件：环境变量 DEV_RESET_TOKEN 被设置且非空，请求头 X-Dev-Reset 必须等于该值。
    生产容器绝对不要设置 DEV_RESET_TOKEN。
    """
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


@router.post("/dev-reset-password")
def dev_reset_password(
    body: DevResetBody,
    session: Session = Depends(get_session),
    x_dev_reset: Annotated[str | None, Header(alias="X-Dev-Reset")] = None,
):
    """开发专用：admin 密码忘了的话，本地一行 curl 就能重置。

    安全门：环境变量 DEV_RESET_TOKEN 非空时，请求头 X-Dev-Reset 必须完全匹配；
    DEV_RESET_TOKEN 未设置 / 为空时这个接口直接 403（即使打了 header 也无济于事）。

    生产部署请勿设置 DEV_RESET_TOKEN。
    """
    import os as _os

    expected = (_os.environ.get("DEV_RESET_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="DEV_RESET_TOKEN 未设置，此接口在当前环境不可用")
    if (x_dev_reset or "").strip() != expected:
        raise HTTPException(status_code=403, detail="X-Dev-Reset header 不匹配")

    user = session.exec(select(User).where(User.username == "admin")).first()
    if user is None:
        user = User(
            username="admin",
            password_hash=hash_password(body.password),
            role="admin",
            must_change_password=False,
            enabled=True,
        )
        session.add(user)
    else:
        user.password_hash = hash_password(body.password)
        user.must_change_password = False
        session.add(user)
    session.commit()
    logger.warning("dev-reset-password: 已重置 admin 密码（仅在 DEV_RESET_TOKEN 启用时可用）")
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
