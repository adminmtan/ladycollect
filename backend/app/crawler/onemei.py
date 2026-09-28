"""1mei.live 适配器：列表 URL 构造、详情抓取

支持模式：
- list_all：分页抓首页 /page/N/
- list_search：/search/keyword/ （WP 内置 ?s=kw 兼容）
- list_date：/date/YYYY/MM/ 或 /date/YYYY/MM/DD/
- list_category：/category/slug/
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional
from urllib.parse import urljoin


@dataclass
class ListSpec:
    """一个列表页请求参数"""

    url: str
    page: int = 1


def iter_list_urls(
    base_url: str,
    *,
    kind: str = "list_all",
    keyword: Optional[str] = None,
    date_from: Optional[str] = None,  # YYYY-MM-DD
    date_to: Optional[str] = None,
    category: Optional[str] = None,
    max_pages: int = 20,
) -> Iterator[ListSpec]:
    """按模式生成所有要采集的列表页 URL"""
    base = base_url.rstrip("/")

    if kind == "list_search" and keyword:
        # WP 内置 ?s=kw
        from urllib.parse import quote

        url = f"{base}/?s={quote(keyword)}"
        for p in range(1, max_pages + 1):
            yield ListSpec(url=url if p == 1 else f"{base}/page/{p}/?s={quote(keyword)}", page=p)
        return

    if kind == "list_date":
        # 单日 / 单月
        from datetime import date as _date, timedelta

        if date_from and date_to:
            try:
                d1 = _date.fromisoformat(date_from)
                d2 = _date.fromisoformat(date_to)
            except ValueError:
                d1 = d2 = None
        else:
            d1 = d2 = None

        if d1 and d2:
            d = d1
            while d <= d2:
                yield ListSpec(url=f"{base}/date/{d.year:04d}/{d.month:02d}/{d.day:02d}/", page=1)
                d += timedelta(days=1)
        elif d1:
            yield ListSpec(
                url=f"{base}/date/{d1.year:04d}/{d1.month:02d}/{d1.day:02d}/",
                page=1,
            )
        else:
            # 只传 month
            ym = (date_from or date_to or "").split("-")
            if len(ym) >= 2:
                y, m = ym[0], ym[1]
                yield ListSpec(url=f"{base}/date/{y}/{int(m):02d}/", page=1)
            else:
                yield ListSpec(url=base + "/", page=1)
        return

    if kind == "list_category" and category:
        url = f"{base}/category/{category.strip('/')}/"
        for p in range(1, max_pages + 1):
            yield ListSpec(url=url if p == 1 else f"{base}/category/{category.strip('/')}/page/{p}/", page=p)
        return

    # 默认 list_all：分页首页
    for p in range(1, max_pages + 1):
        yield ListSpec(url=base + ("/" if p == 1 else f"/page/{p}/"), page=p)


def detail_url(base_url: str, post_id: int, slug: str = "") -> str:
    base = base_url.rstrip("/")
    if slug:
        return f"{base}/{post_id}/{slug}/"
    return f"{base}/{post_id}/"
