"""认证工具：密码哈希 + JWT 签发/校验 + FastAPI 依赖"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security.utils import get_authorization_scheme_param
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models import User

logger = logging.getLogger(__name__)

AUTH_COOKIE_NAME = "cp_token"


def _ensure_default_admin(session: Session) -> User:
    """兜底：极端情况下 db.init_db 漏建用户，这里再补"""
    user = session.exec(select(User).where(User.username == "admin")).first()
    if user is None:
        user = User(
            username="admin",
            password_hash="!UNINITIALIZED!",
            role="admin",
            must_change_password=True,
            enabled=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def hash_password(plain: str) -> str:
    """bcrypt 哈希。bcrypt 限长 72 字节——足够绝大多数密码。"""
    if not plain:
        raise ValueError("password 不能为空")
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验密码。占位 hash 直接 False。"""
    if not plain or not hashed or hashed.startswith("!UNINITIALIZED!"):
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user: User) -> str:
    """签发 JWT（HS256 + settings.jwt_secret）。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "uid": user.id,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """解 JWT；过期或非法抛 jwt.* 异常。"""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def _extract_token(
    authorization: Optional[str] = Header(default=None),
    cookie_token: Optional[str] = Cookie(default=None, alias=AUTH_COOKIE_NAME),
) -> Optional[str]:
    """优先取 Authorization: Bearer xx，其次 cookie"""
    if authorization:
        scheme, param = get_authorization_scheme_param(authorization)
        if scheme.lower() == "bearer" and param:
            return param
    if cookie_token:
        return cookie_token
    return None


def get_current_user(
    token: Optional[str] = Depends(_extract_token),
    session: Session = Depends(get_session),
) -> User:
    """FastAPI 依赖：从 Bearer/cookie 取 JWT，解析出当前用户。"""
    if settings.auth_disabled:
        return _ensure_default_admin(session)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 无效")
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token 缺少主体")
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None or not user.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已停用")
    if user.password_hash.startswith("!UNINITIALIZED!"):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="系统尚未初始化密码")
    return user


def is_public_path(path: str) -> bool:
    """检查路径是否在白名单内（前缀匹配）"""
    prefixes = [p.strip() for p in settings.auth_public_paths.split(",") if p.strip()]
    return any(path == p or path.startswith(p) for p in prefixes)
