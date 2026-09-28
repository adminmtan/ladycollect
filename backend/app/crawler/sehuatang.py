"""sehuatang.org 适配器（Discuz! X3.4 论坛）

支持模式：
- list_forum：按板块 fid 分页抓取，URL 模式 `forum-{fid}-{page}.html`

与 1mei 的差异：
- 列表页是 `<table>` + `<tbody id="normalthread_{tid}">`，无 `article.excerpt`
- 详情页 magnet/torrent 是 `<li>纯文本</li>` 不是 `<a href>` 标签
- 有年龄验证警告页（浏览器自动通过）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass
class ListSpec:
    """一个列表页请求参数"""

    url: str
    page: int = 1


def iter_forum_list_urls(
    base_url: str,
    *,
    fid: Optional[str] = None,
    max_pages: int = 20,
) -> Iterator[ListSpec]:
    """按板块 fid 生成所有要采集的列表页 URL。

    fid 来自 task.category（兼容 1mei 的字段命名）。
    """
    if not fid:
        raise ValueError("sehuatang.list_forum 必须提供 category=fid")

    base = base_url.rstrip("/")
    for p in range(1, max_pages + 1):
        yield ListSpec(url=f"{base}/forum-{fid}-{p}.html", page=p)


def detail_url(base_url: str, tid: int, slug: str = "") -> str:
    """Discuz 帖子详情页 URL。slug 不参与（Discuz 不需要）。"""
    base = base_url.rstrip("/")
    return f"{base}/thread-{tid}-1-1.html"
