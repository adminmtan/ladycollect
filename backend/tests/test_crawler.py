"""单元测试：extractor / parser / onemei 适配器（不依赖 CloakBrowser）"""
from html import escape

import pytest

from app.crawler.extractor import extract_links
from app.crawler.onemei import iter_list_urls, detail_url
from app.crawler.parser import (
    _parse_iso_date,
    _parse_relative_time,
    parse_detail_html,
    parse_list_html,
)


def test_extract_magnet_basic():
    html = "<p>magnet:?xt=urn:btih:4ac81c5b08a6332e91e317754c753b560dbc49e8</p>"
    out = extract_links(html)
    assert len(out["magnet"]) == 1
    assert out["magnet"][0].startswith("magnet:?xt=urn:btih:4ac81")


def test_extract_magnet_encoded():
    """验证 URL 编码形态 magnet:?xt%3Durn%3Abtih%3Axxxx 也能识别"""
    html = "<p>magnet:?xt%3Durn%3Abtih%3A4ac81c5b08a6332e91e317754c753b560dbc49e8</p>"
    out = extract_links(html)
    assert len(out["magnet"]) == 1
    # 规范化后使用标准形态
    assert out["magnet"][0] == "magnet:?xt=urn:btih:4ac81c5b08a6332e91e317754c753b560dbc49e8"


def test_extract_ed2k():
    html = '<a href="ed2k://|file|name.zip|1234|ABCD/">x</a>'
    out = extract_links(html)
    assert len(out["ed2k"]) == 1
    assert out["ed2k"][0].startswith("ed2k://")


def test_parse_relative_time_hours():
    from datetime import date as _date

    assert _parse_relative_time("9小时前") == _date.today()


def test_parse_relative_time_days():
    from datetime import date as _date, timedelta

    assert _parse_relative_time("3天前") == _date.today() - timedelta(days=3)


def test_parse_iso_date():
    from datetime import date as _date

    assert _parse_iso_date("2026-09-12 发布") == _date(2026, 9, 12)


def test_parse_list_html_minimal():
    html = """
    <html><body>
      <article class="excerpt">
        <header><h2><a href="https://1mei.live/12345/test-slug/">测试标题</a></h2></header>
        <p><span class="muted">@author</span><span class="muted"> 1天前 </span></p>
      </article>
    </body></html>
    """
    items = parse_list_html(html, "https://1mei.live")
    assert len(items) == 1
    it = items[0]
    assert it.post_id == 12345
    assert it.slug == "test-slug"
    assert it.title == "测试标题"


def test_parse_detail_extracts_magnet_and_title():
    html = """
    <html><body>
      <div class="content">
        <h1 class="article-title">详情标题</h1>
        <p>正文</p>
        <p>magnet:?xt=urn:btih:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa</p>
      </div>
    </body></html>
    """
    d = parse_detail_html(html, "https://1mei.live")
    assert d.title == "详情标题"
    assert len(d.magnet) == 1
    assert d.magnet[0].endswith("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")


def test_iter_list_urls_list_all():
    urls = list(iter_list_urls("https://1mei.live", kind="list_all", max_pages=3))
    assert urls[0].url == "https://1mei.live/"
    assert urls[1].url == "https://1mei.live/page/2/"
    assert urls[2].url == "https://1mei.live/page/3/"


def test_iter_list_urls_list_search():
    urls = list(iter_list_urls("https://1mei.live", kind="list_search", keyword="AI 漫画", max_pages=2))
    assert "s=" in urls[0].url and "AI" in urls[0].url


def test_iter_list_urls_list_date_range():
    urls = list(
        iter_list_urls(
            "https://1mei.live",
            kind="list_date",
            date_from="2026-09-10",
            date_to="2026-09-12",
        )
    )
    # 3 天 → 3 个 URL
    assert len(urls) == 3
    assert "/2026/09/10/" in urls[0].url


def test_detail_url():
    assert detail_url("https://1mei.live", 123, "abc") == "https://1mei.live/123/abc/"
