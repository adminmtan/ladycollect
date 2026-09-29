"""FastAPI 应用入口"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import api as api_pkg  # noqa
from app.api import posts, sites, stats, tasks, filter_rules, feedback
from app.api import auth as auth_api
from app.api import settings as settings_api
from app.auth import is_public_path
from app.config import settings
from app.db import init_db
from app.logging_setup import setup_logging

# 必须在任何 logger.info 之前调用，确保所有日志走文件 + stderr 双通道
LOGS_DIR = setup_logging(
    logs_dir=Path("/app/data/logs"),
    level=settings.log_level,
    max_bytes=int(os.environ.get("LOG_MAX_BYTES", 20 * 1024 * 1024)),
    backup_count=int(os.environ.get("LOG_BACKUP_COUNT", 5)),
    keep_days=int(os.environ.get("LOG_KEEP_DAYS", 30)),
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("数据库初始化完成")
    # 启动后台调度器
    try:
        from app.scheduler import bootstrap
        bootstrap()
    except Exception as e:
        logger.warning("调度器启动失败（不影响主功能）：%s", e)
    yield


app = FastAPI(
    title="1mei.live 采集管理面板",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS（开发期放开；生产建议同源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    """认证网关：除公开路径外，所有 /api/* 都要求 JWT。
    前端 SPA 静态资源不要求（LoginView 直接可达）。"""
    path = request.url.path
    # 静态资源 + SPA 路由 + 健康检查 + auth 白名单 → 放行
    if (
        not path.startswith("/api/")
        or path == "/api/health"
        or is_public_path(path)
    ):
        return await call_next(request)
    # auth_disabled 整站放行（调试）
    if settings.auth_disabled:
        return await call_next(request)
    # 强制要求 Bearer/cookie
    from fastapi.security.utils import get_authorization_scheme_param
    from app.auth import AUTH_COOKIE_NAME, decode_token
    from sqlmodel import Session as _S  # noqa
    from sqlmodel import select as _sel
    from app.db import engine as _engine
    from app.models import User as _User

    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    token = None
    if auth:
        scheme, param = get_authorization_scheme_param(auth)
        if scheme.lower() == "bearer" and param:
            token = param
    if not token:
        token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return JSONResponse({"detail": "未登录"}, status_code=401)
    try:
        payload = decode_token(token)
    except Exception:
        return JSONResponse({"detail": "token 无效或已过期"}, status_code=401)
    username = payload.get("sub")
    if not username:
        return JSONResponse({"detail": "token 缺少主体"}, status_code=401)
    # 用户存在 + 未停用 + 已初始化
    with _S(_engine) as s:
        u = s.exec(_sel(_User).where(_User.username == username)).first()
    if u is None or not u.enabled:
        return JSONResponse({"detail": "用户不存在或已停用"}, status_code=401)
    if u.password_hash.startswith("!UNINITIALIZED!"):
        return JSONResponse({"detail": "系统尚未初始化密码"}, status_code=503)
    return await call_next(request)


# API 路由
app.include_router(sites.router)
app.include_router(tasks.router)
app.include_router(posts.router)
app.include_router(stats.router)
app.include_router(filter_rules.router)
app.include_router(feedback.router)
app.include_router(settings_api.router)
app.include_router(auth_api.router)


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.1.0"}


# 前端静态资源（Vite build 输出）
if settings.static_dir.exists() and any(settings.static_dir.iterdir()):
    app.mount(
        "/assets",
        StaticFiles(directory=str(settings.static_dir / "assets")),
        name="assets",
    )

    @app.get("/")
    @app.get("/{path:path}")
    def spa_fallback(path: str = ""):
        """SPA History fallback：未匹配的路径返回 index.html"""
        # 优先匹配真实文件
        candidate = settings.static_dir / path
        if path and candidate.is_file():
            return FileResponse(str(candidate))
        index = settings.static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"msg": "前端尚未构建", "static_dir": str(settings.static_dir)})
else:
    @app.get("/")
    def root_no_static():
        return JSONResponse(
            {
                "msg": "API 服务运行中；前端未构建，请 cd frontend && npm run build",
                "docs": "/docs",
                "openapi": "/openapi.json",
            }
        )
