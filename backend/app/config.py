"""pydantic-settings 应用配置"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录（backend/app/config.py -> backend/app -> backend -> root）
ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    """应用配置（可通过 .env / 环境变量覆盖）"""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # HTTP 服务
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8080)

    # 数据库
    database_url: str = Field(default=f"sqlite:///{DATA_DIR / 'app.db'}")

    # 默认 UA
    default_user_agent: str = Field(
        default="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    )

    # 全局代理（站点级 proxy 优先）
    proxy_url: Optional[str] = Field(default=None)

    # CloakBrowser
    cloakbrowser_license_key: Optional[str] = Field(default=None)
    cloakbrowser_auto_update: bool = Field(default=True)

    # 日志
    log_level: str = Field(default="INFO")

    # 采集任务默认值
    default_max_pages: int = Field(default=20)
    default_max_concurrent: int = Field(default=3)
    default_request_timeout: int = Field(default=30)

    # 浏览器配置目录
    profile_dir: Path = Field(default=DATA_DIR / "profile")

    # AI 关键词提取（OpenAI 兼容 API；留空则降级到本地规则提取）
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_api_key: Optional[str] = Field(default=None)
    openai_model: str = Field(default="gpt-4o-mini")
    openai_timeout: int = Field(default=20)

    # 认证 / JWT
    jwt_secret: str = Field(
        default="",
        description="JWT 签名密钥。Docker 模式下由 entrypoint.sh 生成随机值并写入 /app/data/.jwt_secret",
    )
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=24 * 60, description="token 有效期（分钟），默认 24 小时")
    # 允许免认证的公开路径（前缀形式，逗号分隔）
    auth_public_paths: str = Field(
        default="/api/health,/api/auth/login,/api/auth/setup,/api/auth/initialized,/_internal/",
        description="这些路径前缀不需要 token",
    )
    # 允许匿名访问（调试用）
    auth_disabled: bool = Field(default=False, description="True 时整站放行（生产必须 False）")

    @property
    def static_dir(self) -> Path:
        """前端构建产物目录（FastAPI StaticFiles 挂载）"""
        return BACKEND_DIR / "app" / "static"


settings = Settings()

# 如果 jwt_secret 为空（容器内场景），尝试从持久化文件读取
import os as _os
if not settings.jwt_secret:
    secret_path = DATA_DIR / ".jwt_secret"
    if secret_path.exists():
        try:
            settings.jwt_secret = secret_path.read_text().strip()
        except Exception:
            pass
if not settings.jwt_secret:
    # 最后兜底：本机开发模式，生成一次性 dev secret 并打印 WARNING
    import secrets as _secrets
    settings.jwt_secret = _secrets.token_urlsafe(32)
    logger = logging.getLogger("app.config")
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("app.config").warning(
        "未配置 JWT secret，已生成临时 dev secret。生产请通过 /app/data/.jwt_secret 或 JWT_SECRET env 注入。",
    )

# 确保数据目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.profile_dir.mkdir(parents=True, exist_ok=True)
settings.static_dir.mkdir(parents=True, exist_ok=True)
