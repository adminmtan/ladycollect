"""统一的 CloakBrowser 启动入口

支持两种部署模式：
- 本地模式：直接 launch 持久化 context（默认，Docker 镜像内已带 Chromium）
- CDP 模式：连接外部 cloakserve 容器（多任务隔离更稳）

DrissionPage 通过指定 --browser_path 复用 CloakBrowser 的 Chromium 二进制。
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from app.config import settings as app_settings

logger = logging.getLogger(__name__)


def ensure_cloakbrowser_binary() -> str:
    """确保 CloakBrowser 二进制已下载，返回二进制路径"""
    try:
        from cloakbrowser import ensure_binary, binary_info
    except ImportError as e:
        raise RuntimeError("cloakbrowser 未安装，请 `pip install cloakbrowser`") from e

    info = binary_info() if hasattr(binary_info, "__call__") else None
    if isinstance(info, dict) and info.get("installed"):
        return info.get("binary_path") or _find_binary()

    logger.info("CloakBrowser 二进制不存在，开始下载...")
    ensure_binary()
    return _find_binary()


def _find_binary() -> str:
    """从 ~/.cloakbrowser 下找最新 Chromium.app/Contents/MacOS/Chromium"""
    home = Path(os.path.expanduser("~"))
    cb_root = home / ".cloakbrowser"
    if not cb_root.exists():
        return ""
    # 选最高版本目录
    candidates = sorted(
        [p for p in cb_root.glob("chromium-*") if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    for d in candidates:
        # macOS
        mac = d / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
        if mac.exists():
            return str(mac)
        # Linux
        for name in ("chromium", "Chromium", "chrome"):
            linux = d / name
            if linux.exists() and os.access(linux, os.X_OK):
                return str(linux)
        # Windows
        win = d / "Chromium.exe"
        if win.exists():
            return str(win)
    return ""


@contextmanager
def make_browser(
    *,
    headless: bool = True,
    humanize: bool = False,
    proxy: Optional[str] = None,
    user_agent: Optional[str] = None,
    fingerprint_seed: Optional[int] = None,
    profile_dir: Optional[Path] = None,
    persistent: bool = True,
):
    """上下文管理器：返回 Playwright 兼容的 Browser 或 BrowserContext

    使用示例：
        with make_browser(headless=True) as browser:
            page = browser.new_page()
            page.goto("https://example.com")
    """
    from cloakbrowser import launch, launch_persistent_context

    args: list[str] = []
    if fingerprint_seed:
        args.append(f"--fingerprint={fingerprint_seed}")

    # 代理优先级：传入 > 全局 settings
    proxy_url = proxy or app_settings.proxy_url

    profile = str(profile_dir or app_settings.profile_dir)
    Path(profile).mkdir(parents=True, exist_ok=True)

    if persistent:
        ctx = launch_persistent_context(
            profile,
            headless=headless,
            humanize=humanize,
            proxy=proxy_url,
            user_agent=user_agent,
            args=args,
        )
        try:
            yield ctx
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    else:
        browser = launch(
            headless=headless,
            humanize=humanize,
            proxy=proxy_url,
            user_agent=user_agent,
            args=args,
        )
        try:
            yield browser
        finally:
            try:
                browser.close()
            except Exception:
                pass


def get_drissionpage_browser_path() -> str:
    """给 DrissionPage 提供 CloakBrowser 的 Chromium 路径"""
    p = _find_binary()
    if p:
        return p
    # 未找到则触发下载
    return ensure_cloakbrowser_binary()
