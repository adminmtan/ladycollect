"""HTML 解析工具：Scrapling + 原生 BS4 兜底"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date as date_t
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class PostMeta:
    """列表页抽取出的文章元数据"""

    post_id: int
    slug: str
    url: str
    title: str
    author: Optional[str] = None
    cover: Optional[str] = None
    summary: Optional[str] = None
    post_date: Optional[date_t] = None
    raw: dict = field(default_factory=dict)


@dataclass
class PostDetail:
    """详情页抽取出的链接与补充信息"""

    title: str
    magnet: list[str] = field(default_factory=list)
    ed2k: list[str] = field(default_factory=list)
    post_date: Optional[date_t] = None
    author: Optional[str] = None
    cover: Optional[str] = None
    raw: dict = field(default_factory=dict)


def _post_id_from_url(url: str) -> Optional[int]:
    m = re.search(r"/(\d+)/", url)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _slug_from_url(url: str) -> str:
    p = urlparse(url)
    parts = [seg for seg in p.path.split("/") if seg]
    # 取最后一个非纯数字段
    for seg in reversed(parts):
        if not seg.isdigit():
            return seg
    return parts[-1] if parts else ""


# 详情页封面抽取：过滤头像 / 文件类型 / 装饰图
_COVER_EXCLUDE_PATTERNS = [
    # 头像
    "avatar",
    "/uc_server/",
    # 站点装饰 / 文件类型图标
    "static/image/common/",
    "static/image/filetype/",
    "static/image/smiley/",
    "static/image/feed/",
    # 表情 / 贴纸
    "smiley",
    "sticker",
    "emoji",
]


def _is_cover_candidate(src: str) -> bool:
    """判断 src 是否像一张帖子封面（不是头像/装饰图）"""
    if not src:
        return False
    s = src.lower()
    # data: / javascript: / 空
    if s.startswith(("data:", "javascript:", "#")):
        return False
    # 黑名单
    for pat in _COVER_EXCLUDE_PATTERNS:
        if pat in s:
            return False
    # 必须像图片
    return any(s.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))


def _extract_cover(soup, base_url: str) -> Optional[str]:
    """从详情页抽取第一张「内容图」当封面。

    优先级：
      1) 正文区（.pcb / .t_f / #post_message / article .entry-content / div.article-content）内 img
      2) 兜底：全页第一张非装饰图
    """
    # 优先级：Discuz → 1mei
    content_selectors = [
        ".pcb img",        # Discuz 正文
        ".t_f img",        # Discuz 正文
        "#post_message img",  # Discuz 正文
        "div.article-content img",  # 1mei
        "div.entry-content img",
        "article .content img",
        ".post-content img",
        ".postbody img",
        ".post-text img",
    ]
    seen: set[str] = set()
    for sel in content_selectors:
        for img in soup.select(sel):
            src = img.get("src") or img.get("data-src") or img.get("file") or ""
            if not src or src in seen:
                continue
            seen.add(src)
            if _is_cover_candidate(src):
                return urljoin(base_url, src)

    # 兜底：全页第一张符合的
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or src in seen:
            continue
        if _is_cover_candidate(src):
            return urljoin(base_url, src)

    return None


def _parse_relative_time(text: str, today: Optional[date_t] = None) -> Optional[date_t]:
    """尝试从 "X 小时前 / X 天前 / X 分钟前" 推出日期"""
    if not text:
        return None
    from datetime import date as _date, timedelta

    t = text.strip()
    m = re.match(r"^(\d+)\s*(分钟|分|小时|天|日|周|月|年)前", t)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    today = today or _date.today()
    if unit in ("分钟", "分"):
        return today
    if unit == "小时":
        return today
    if unit in ("天", "日"):
        return today - timedelta(days=n)
    if unit == "周":
        return today - timedelta(weeks=n)
    if unit == "月":
        try:
            year = today.year
            month = today.month - n
            while month <= 0:
                month += 12
                year -= 1
            return _date(year, month, min(today.day, 28))
        except Exception:
            return None
    if unit == "年":
        try:
            return _date(today.year - n, today.month, min(today.day, 28))
        except Exception:
            return None
    return None


def _parse_iso_date(text: str) -> Optional[date_t]:
    from datetime import date as _date

    if not text:
        return None
    m = re.search(r"(\d{4})[-./年](\d{1,2})[-./月](\d{1,2})", text)
    if m:
        try:
            return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def parse_list_html(html_text: str, base_url: str) -> list[PostMeta]:
    """解析列表页，提取每条文章的元数据"""
    soup = BeautifulSoup(html_text or "", "lxml")
    results: list[PostMeta] = []

    for art in soup.select("article.excerpt"):
        a = art.select_one("header h2 a")
        if not a:
            # 兜底：缩略图上的链接
            a = art.select_one("a.thumbnail")
        if not a:
            continue

        url = urljoin(base_url, a.get("href", ""))
        if not url:
            continue
        post_id = _post_id_from_url(url)
        slug = _slug_from_url(url)
        if not post_id:
            continue

        title = (a.get_text() or a.get("title") or "").strip()

        author_el = art.select_one(".muted a[href*='/author/']")
        author = author_el.get_text(strip=True) if author_el else None

        cover_el = art.select_one("a.thumbnail img")
        cover = None
        if cover_el:
            cover = cover_el.get("src") or cover_el.get("data-src")
            if cover:
                cover = urljoin(base_url, cover)

        # post_date：先尝试相对时间，失败再尝试 ISO
        post_date: Optional[date_t] = None
        for muted in art.select(".muted"):
            txt = muted.get_text(" ", strip=True)
            post_date = _parse_relative_time(txt) or _parse_iso_date(txt)
            if post_date:
                break

        # 摘要
        note = art.select_one("p.note")
        summary = note.get_text(strip=True) if note else None

        results.append(
            PostMeta(
                post_id=post_id,
                slug=slug,
                url=url,
                title=title,
                author=author,
                cover=cover,
                summary=summary,
                post_date=post_date,
                raw={"list_html_excerpt": str(art)[:500]},
            )
        )

    # 兜底：如果没匹配到 excerpt，用 URL 模式兜底
    if not results:
        seen = set()
        for a in soup.select("a[href*='://'][href*='/" + str(_) + "/']" for _ in range(1, 99999)):
            pass  # noop
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "://" not in href:
                href = urljoin(base_url, href)
            pid = _post_id_from_url(href)
            if not pid or pid in seen:
                continue
            if base_url.split("//", 1)[-1].split("/", 1)[0] not in href:
                continue
            seen.add(pid)
            text = a.get_text(strip=True)
            if not text or len(text) < 4:
                continue
            results.append(
                PostMeta(
                    post_id=pid,
                    slug=_slug_from_url(href),
                    url=href,
                    title=text,
                )
            )

    return results


def parse_detail_html(html_text: str, base_url: str) -> PostDetail:
    """解析详情页：标题、magnet、ed2k、日期"""
    from app.crawler.extractor import extract_links

    soup = BeautifulSoup(html_text or "", "lxml")

    title = ""
    h1 = soup.select_one("h1.article-title")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        # 兜底：<title>
        t = soup.title.string if soup.title else ""
        if t:
            # 去除「 - 站点名」后缀
            title = re.sub(r"\s*[-_|].*$", "", t).strip()

    # 抽取链接（对正文 + 整页都跑一遍，提高命中率）
    content_html = ""
    # 取最长的 div.content / div.article-content
    candidates = soup.select("div.article-content") + soup.select("div.content")
    if candidates:
        content_el = max(candidates, key=lambda el: len(el.get_text()))
        content_html = str(content_el)
    full_html = html_text or ""
    links = extract_links((content_html + "\n" + full_html))

    # 日期
    post_date: Optional[date_t] = None
    time_el = soup.select_one("article time, .article-header time, header time")
    if time_el:
        ds = time_el.get("datetime") or time_el.get_text(" ", strip=True)
        post_date = _parse_relative_time(ds) or _parse_iso_date(ds)
    # 兜底：URL slug 中含日期（如 ...2026-09-12...）
    if not post_date:
        for a in soup.select("a[href]"):
            ds = _parse_iso_date(a.get("href", ""))
            if ds:
                post_date = ds
                break

    author = None
    auth_el = soup.select_one("a[href*='/author/']")
    if auth_el:
        author = auth_el.get_text(strip=True)

    # 封面：正文里第一张「内容图」（非头像 / 非文件类型图标）
    cover = _extract_cover(soup, base_url)

    return PostDetail(
        title=title,
        magnet=links["magnet"],
        ed2k=links["ed2k"],
        post_date=post_date,
        author=author,
        cover=cover,
        raw={"title_h1": bool(h1)},
    )


def parse_discuz_list_html(html_text: str, base_url: str) -> list[PostMeta]:
    """解析 Discuz! 论坛板块列表页（tbody[id^='normalthread_']）。

    每行结构：
      <tbody id="normalthread_{tid}">
        <tr>
          <th><a class="s xst" href="thread-{tid}-1-1.html">{title}</a></th>
          <td class="by">{author}<br>{time}</td>
          ...
        </tr>
      </tbody>
    """
    from app.crawler.parser import _post_id_from_url, _slug_from_url

    soup = BeautifulSoup(html_text or "", "lxml")
    results: list[PostMeta] = []

    for tr in soup.select("tbody[id^='normalthread_']"):
        a = tr.select_one("th a.s.xst")
        if not a:
            continue
        href = a.get("href", "")
        url = urljoin(base_url, href)
        if not url:
            continue
        post_id = _post_id_from_url(url)
        if not post_id:
            # Discuz URL 形如 thread-{tid}-1-1.html，post_id 在第 2 段
            m = re.search(r"thread-(\d+)-", href)
            if m:
                post_id = int(m.group(1))
            else:
                continue

        title = (a.get_text() or "").strip()

        # 作者 + 时间
        author = None
        post_date: Optional[date_t] = None
        by_el = tr.select_one("td.by")
        if by_el:
            parts = [s.strip() for s in by_el.get_text("\n").splitlines() if s.strip()]
            if parts:
                author = parts[0]

            # Discuz! X3.4 列表页时间通常在 td.by 第二行：
            #   <em><span title="2026-09-30 12:34">3 小时前</span></em>
            # 或纯文本 "2026-9-30"。先取 span[title]（ISO 精确），再 fallback 到 span 文本，
            # 最后 fallback 到 td.by 第二行纯文本。
            time_attr: Optional[str] = None
            span_title = by_el.select_one("em span[title]")
            if span_title and span_title.get("title"):
                time_attr = span_title.get("title")
            if not time_attr:
                any_span = by_el.select_one("em span")
                if any_span:
                    time_attr = any_span.get_text(" ", strip=True)
            if not time_attr and len(parts) >= 2:
                time_attr = parts[1]
            if time_attr:
                post_date = _parse_relative_time(time_attr) or _parse_iso_date(time_attr)

        results.append(
            PostMeta(
                post_id=post_id,
                slug=str(post_id),
                url=url,
                title=title,
                author=author,
                cover=None,
                summary=None,
                post_date=post_date,
                raw={"list_row": str(tr)[:300]},
            )
        )

    return results


def parse_discuz_detail_html(html_text: str, base_url: str) -> PostDetail:
    """解析 Discuz! 帖子详情页。

    与 1mei 不同：
      - magnet 是 `.blockcode li` 纯文本，不是 <a href="magnet:">
      - 标题来自 `<h1 class="ts">#thread_subject` 或 h1 / document.title
      - 时间在 `.authi em` 或 `<em id="authorposton{...}">`
    """
    from app.crawler.extractor import extract_links

    soup = BeautifulSoup(html_text or "", "lxml")

    # 标题
    title = ""
    title_el = soup.select_one("#thread_subject, h1.ts")
    if title_el:
        title = title_el.get_text(strip=True)
    if not title:
        h1 = soup.select_one("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        t = soup.title.string if soup.title else ""
        if t:
            title = re.sub(r"\s*[-_|].*$", "", t).strip()

    # magnet / ed2k：优先抽取所有 <a href>，再扫正文 text 找磁力（Discuz 用 .blockcode li 装）
    links = extract_links(html_text or "")
    magnet = list(links.get("magnet", []))
    ed2k = list(links.get("ed2k", []))

    # 兜底：扫描正文文本，找 magnet:?xt=urn:btih:...
    if not magnet:
        for li in soup.select(".blockcode li, .pcb li, .t_f li"):
            txt = li.get_text(strip=True)
            if txt.startswith("magnet:?xt=urn:btih:"):
                magnet.append(txt)
            elif txt.startswith("ed2k://"):
                ed2k.append(txt)

    # 发布日期
    post_date = None
    time_el = soup.select_one(".authi em, em[id^='authorposton']")
    if time_el:
        ds = time_el.get("title") or time_el.get_text(" ", strip=True)
        post_date = _parse_relative_time(ds) or _parse_iso_date(ds)

    # 作者
    author = None
    auth_el = soup.select_one(".authi a, .postauthor a")
    if auth_el:
        author = auth_el.get_text(strip=True)

    # 封面：Discuz 详情正文里第一张图（filter 用户头像 / 文件类型图标）
    cover = _extract_cover(soup, base_url)

    return PostDetail(
        title=title,
        magnet=magnet,
        ed2k=ed2k,
        post_date=post_date,
        author=author,
        cover=cover,
        raw={"has_blockcode": bool(soup.select(".blockcode"))},
    )


def parse_pagination_max(html_text: str, base_url: str) -> int:
    """从分页中推断最大页码"""
    soup = BeautifulSoup(html_text or "", "lxml")
    nums: list[int] = []
    for el in soup.select(".pagination .page-numbers"):
        t = el.get_text(strip=True)
        if t.isdigit():
            nums.append(int(t))
    # 兜底：匹配形如 /page/123/ 的链接
    for a in soup.select("a[href]"):
        m = re.search(r"/page/(\d+)/?", a.get("href", ""))
        if m:
            try:
                nums.append(int(m.group(1)))
            except ValueError:
                pass
    return max(nums) if nums else 1


def find_next_page_url(html_text: str, base_url: str, current_page: int) -> Optional[str]:
    """找下一页 URL；找不到返回 None"""
    soup = BeautifulSoup(html_text or "", "lxml")
    # 优先 .pagination .next-page
    nxt = soup.select_one(".pagination li.next-page a, .pagination a.next")
    if nxt and nxt.get("href"):
        return urljoin(base_url, nxt["href"])
    # 兜底：构造 /page/N+1/
    return urljoin(base_url, f"/page/{current_page + 1}/")
