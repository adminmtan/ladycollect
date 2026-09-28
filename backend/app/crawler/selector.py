"""目标站 CSS/XPath 选择器（集中维护，方便按站调整）"""
from __future__ import annotations


# 列表页（首页、归档、分类、搜索共用一套 article.excerpt 结构）
LIST_ITEM = "article.excerpt"
LIST_TITLE_LINK = "article.excerpt header h2 a"
LIST_TITLE_FALLBACK = "article.excerpt a.thumbnail"
LIST_URL_RE = r"^https?://[^/]+/(\d+)/([^/]+)/?$"

LIST_AUTHOR = "article.excerpt .muted a[href*='/author/']"
LIST_META_BLOCK = "article.excerpt p span.muted"

# 详情页
DETAIL_TITLE = "h1.article-title"
DETAIL_CONTENT = "div.article-content, div.content"
DETAIL_TIME = "article time, .article-header time, header time"

# 分页
PAGINATION_NEXT = ".pagination a.next, .pagination li.next-page a, a.next.page-numbers"
PAGINATION_NUMBERS = ".pagination .page-numbers"
