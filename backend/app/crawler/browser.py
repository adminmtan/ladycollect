"""基于 CloakBrowser 的浏览器采集入口。

为什么用 CloakBrowser（替代 DrissionPage）：
- CloakBrowser 是 C++ source-level patch 的 Chromium（73 处指纹 patch：canvas/WebGL/audio/GPU/CDP），
  Cloudflare Turnstile managed challenge 自动通过（官方测试 PASS，2026-09 Chromium 152）
- 返回标准 Playwright Browser 对象，API 100% 兼容 → `_DPAdapter` 只是 thin wrapper
- 持久 profile（launch_persistent_context）→ cf_clearance cookie 跨 session 复用

runtime evidence（2026-10-01 实测，sehuatang.org）：
- 首次启动（profile 空）→ GOTO 1.3s, title='SEHUATANG.ORG', 含 cf-beacon → CF 直接信任
  （DrissionPage 同样情况需要等 30-60s + 经常失败）
- 第二次启动（profile 已有 cf_clearance）→ GOTO 1.5s, cookies 持久化 OK
- 列表页 199 个 thread- 链接能稳定抓到

为什么从 DrissionPage 切换回 CloakBrowser：
- 之前 e205047 commit 切到 DrissionPage 是因为 cloakbrowser 在 Docker 里 resolver graph 冲突
  （cryptography 47+ 触发 maturin 构建，runtime 镜像没有 Rust toolchain）
- 现在改用 `pip install cloakbrowser --no-deps` 绕过（46ab4db commit），cloakbrowser 复用已有 cryptography/playwright
- 加上实测证明 CloakBrowser 过 CF 显著优于 DrissionPage，**永久解决 CF 拦截**

接口保持：`make_page` 仍是上下文管理器，返回的对象有 `.html` / `.url` / `.get()` / `.wait_loaded()`，
让 runner.py 完全无需改动。
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from app.config import settings as app_settings

logger = logging.getLogger(__name__)


class _PlaywrightAdapter:
    """把 Playwright Page 包成 runner.py 期望的 API 表面：
    .get(url, timeout=...) / .html / .url / .wait_loaded(selector) / .close() / .raw（runner 内部使用）

    Playwright 的标准 API：
        page.goto(url, timeout=30000, wait_until='domcontentloaded')
        page.content() → str (返回 document.documentElement.outerHTML)
        page.url
        page.locator('selector').first / .count() / .click()
    """

    __slots__ = ("_page", "_owns_page", "_ctx")

    def __init__(self, pw_page, owns_page: bool = True, ctx=None):
        self._page = pw_page
        self._owns_page = owns_page
        self._ctx = ctx

    def get(self, url: str, *, timeout: int = 30, **kwargs) -> None:
        # Playwright timeout 单位是毫秒
        # wait_until='domcontentloaded' 触发快（CF challenge JS 跑完后 CF 会再次 302/200 到真实页）
        self._page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded", **kwargs)

    def wait_loaded(self, selector: str, *, timeout: int = 30) -> bool:
        """等指定 CSS selector 的元素出现。Playwright 用 page.locator().count() 轮询。

        返回 True 表示至少一个元素加载完成；False 表示 timeout。
        Playwright 的 wait_for_selector 也行，但 runner.py 已有 try/except 兜底，
        所以用 locator().count() + 手动 sleep 更兼容。
        """
        import time
        deadline = time.time() + timeout
        sel = selector  # runner.py 传的是 CSS selector，直接用
        while time.time() < deadline:
            try:
                if self._page.locator(sel).count() > 0:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    @property
    def html(self) -> str:
        # runner.py 用 page.html 取完整 HTML
        return self._page.content()

    @property
    def url(self) -> str:
        return self._page.url

    @property
    def raw(self):
        """需要直接调 Playwright 底层方法时（如 page.locator('css:a.enter-btn')）"""
        return self._page

    def title(self) -> str:
        # Playwright page.title() 是 method，DrissionPage 是 property，适配统一为 method
        return self._page.title()

    def close(self) -> None:
        if self._owns_page:
            try:
                self._page.close()
            except Exception:
                pass


@contextmanager
def make_page(
    *,
    headless: bool = True,
    proxy: Optional[str] = None,
    user_agent: Optional[str] = None,
    profile_dir: Optional[Path] = None,
) -> Iterator[_PlaywrightAdapter]:
    """上下文管理器：返回一个 Page-like 适配器（.get/.html/.url/.close）。

    headless: True = headless 模式（CloakBrowser headless 也过 CF，C++ patch 抹掉 headless 指纹）
    proxy: HTTP/SOCKS5 代理 URL；为空则用 app_settings.proxy_url
    user_agent: 浏览器 UA；为空用 CloakBrowser 默认（Chrome 152）
    profile_dir: 持久化 user_data_dir，跨 session 复用 cookies（含 cf_clearance）
    """
    try:
        from cloakbrowser import launch_persistent_context
    except ImportError as e:
        raise RuntimeError(
            "cloakbrowser 未安装。请运行：pip install cloakbrowser --no-deps\n"
            "（cloakbrowser 必须在 pyproject 之外安装，--no-deps 避免与 DrissionPage resolver 冲突）"
        ) from e

    proxy_url = proxy or app_settings.proxy_url
    profile = profile_dir or app_settings.profile_dir
    Path(profile).mkdir(parents=True, exist_ok=True)

    extra_args = ["--no-proxy-server"] if not proxy_url else None
    if extra_args is None:
        extra_args = []

    ctx = None
    page = None
    try:
        logger.info(
            "CloakBrowser 启动 profile=%s headless=%s proxy=%s ua=%s",
            profile, headless, bool(proxy_url), "Chrome152" if not user_agent else "custom",
        )
        ctx = launch_persistent_context(
            user_data_dir=str(profile),
            headless=headless,
            proxy=proxy_url,
            args=extra_args,
            # humanize=True 启用 Bézier 鼠标轨迹 + 自然键盘 + 滚动物理；
            # CF behavioral scoring 显著降低 challenge 出现频率
            humanize=True,
        )
        page = ctx.new_page()
        if user_agent:
            page.set_extra_http_headers({"User-Agent": user_agent})
        yield _PlaywrightAdapter(page, owns_page=True, ctx=ctx)
    except Exception as launch_err:
        logger.exception("CloakBrowser 启动失败: %s", launch_err)
        raise
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        if ctx is not None:
            try:
                ctx.close()
            except Exception:
                pass