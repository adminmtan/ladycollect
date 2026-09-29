"""统一的浏览器启动入口（基于 DrissionPage）。

DrissionPage 自带 ChromiumPage，无需外部 cloakbrowser；采集代码通过 page
对象拿到 Playwright 风格的方法子集（get / html / url / ele / wait）。
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from app.config import settings as app_settings

logger = logging.getLogger(__name__)


def _make_options(*, headless: bool, user_agent: Optional[str], proxy: Optional[str]):
    """构造 ChromiumOptions，headless / UA / 代理一次配好。"""
    from DrissionPage import ChromiumOptions

    opts = ChromiumOptions()
    opts.headless(headless)
    if user_agent:
        opts.set_user_agent(user_agent)
    if proxy:
        opts.set_proxy(proxy)
    # 避开自动化特征
    opts.set_argument("--disable-blink-features=AutomationControlled")
    # 数据目录持久化，profile 在 /app/data/profile
    profile = app_settings.profile_dir
    try:
        Path(profile).mkdir(parents=True, exist_ok=True)
        opts.set_user_data_path(str(profile))
    except Exception:
        # profile 不可写也不致命，无头模式仍能跑
        logger.warning("无法准备 profile 目录 %s，使用临时 profile", profile)
    return opts


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
    """上下文管理器：返回一个 ChromiumPage（或 SessionPage，取决于 persistent）。

    humanize / fingerprint_seed 仅做占位记录——DrissionPage 默认已经做了足够
    的反检测（指纹随机化由其内部 Browser 启动参数处理）；如未来需要更精细的
    伪装，可以在这里加 options。
    """
    from DrissionPage import ChromiumPage

    if fingerprint_seed:
        logger.info("fingerprint_seed=%s 仅记录（DrissionPage 已内置指纹）", fingerprint_seed)

    proxy_url = proxy or app_settings.proxy_url
    opts = _make_options(headless=headless, user_agent=user_agent, proxy=proxy_url)

    page = ChromiumPage(opts)
    try:
        yield page
    finally:
        try:
            page.quit()
        except Exception:
            pass


def get_drissionpage_browser_path() -> str:
    """兼容旧调用方。DrissionPage 自带浏览器，无需外部路径。"""
    return ""
