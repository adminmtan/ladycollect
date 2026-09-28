"""Pydantic schema（API 入参/出参）"""
from __future__ import annotations

from datetime import date as date_t, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict


# ============== Site ==============
class SiteBase(BaseModel):
    name: str
    host: str
    base_url: str
    user_agent: Optional[str] = None
    cookies: Optional[str] = None
    proxy: Optional[str] = None
    fingerprint_seed: Optional[int] = None
    adapter: Optional[str] = Field(default="onemei", description="onemei | sehuatang")
    # 色花堂等论坛专属：板块 FID + 自定义 URL 列表（站点级）
    forum_fid: Optional[str] = Field(default=None, description="Discuz 板块 FID（仅 sehuatang 等论坛站）")
    list_urls: Optional[list[str]] = Field(default=None, description="自定义列表 URL 列表（站点级，每行一个）")
    # 注意：站点级 include/exclude 关键词已迁移到 filter_rules + filter_keywords
    # 列保留在 sites 表但 API 不再读写，runner 也不再读取
    enabled: bool = True
    note: Optional[str] = None


class SiteCreate(SiteBase):
    pass


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    base_url: Optional[str] = None
    user_agent: Optional[str] = None
    cookies: Optional[str] = None
    proxy: Optional[str] = None
    fingerprint_seed: Optional[int] = None
    adapter: Optional[str] = None
    forum_fid: Optional[str] = None
    list_urls: Optional[list[str]] = None
    enabled: Optional[bool] = None
    note: Optional[str] = None


class SiteRead(SiteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ============== Task ==============
class TaskBase(BaseModel):
    site_ids: list[int] = Field(description="要采集的站点 ID 列表（多站点）")
    name: str
    kind: str = Field(description="list_all | list_search | list_date | list_category")
    keyword: Optional[str] = None
    date_from: Optional[date_t] = None
    date_to: Optional[date_t] = None
    category: Optional[str] = None
    max_pages: int = 20
    max_concurrent: int = 3
    only_with_links: bool = True
    cron: Optional[str] = Field(default=None, description="5-6 字段 cron 表达式")
    schedule_enabled: bool = False
    name_template: Optional[str] = Field(default=None, description="Job 名模板，支持 {date} {ymd} {task}")


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    site_ids: Optional[list[int]] = None
    name: Optional[str] = None
    kind: Optional[str] = None
    keyword: Optional[str] = None
    date_from: Optional[date_t] = None
    date_to: Optional[date_t] = None
    category: Optional[str] = None
    max_pages: Optional[int] = None
    max_concurrent: Optional[int] = None
    only_with_links: Optional[bool] = None
    cron: Optional[str] = None
    schedule_enabled: Optional[bool] = None
    name_template: Optional[str] = None


class TaskRead(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    created_at: datetime
    # 当前正在跑的 Job id（如果有）。前端用来决定显示「停止」按钮
    running_job_id: Optional[int] = None


# ============== Job ==============
class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    display_name: Optional[str] = None
    status: str
    progress_pages: int
    progress_posts: int
    posts_saved: int
    error: Optional[str]
    log: Any
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime


# ============== Post ==============
class PostBase(BaseModel):
    title: str
    author: Optional[str] = None
    post_date: Optional[date_t] = None
    cover: Optional[str] = None
    summary: Optional[str] = None
    magnet: list[str] = []
    ed2k: list[str] = []


class PostRead(PostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    task_id: Optional[int]
    job_id: Optional[int]
    post_id: int
    slug: str
    url: str
    created_at: datetime
    updated_at: datetime


class PostQuery(BaseModel):
    site_id: Optional[int] = None
    keyword: Optional[str] = None
    date_from: Optional[date_t] = None
    date_to: Optional[date_t] = None
    has_magnet: Optional[bool] = None
    has_ed2k: Optional[bool] = None
    page: int = 1
    page_size: int = 24


class PostPage(BaseModel):
    items: list[PostRead]
    total: int
    page: int
    page_size: int


class CopyLinksRequest(BaseModel):
    post_ids: list[int]
    kinds: list[str] = Field(default=["magnet", "ed2k"], description="magnet | ed2k")


class CopyLinksResponse(BaseModel):
    magnet: list[str] = []
    ed2k: list[str] = []


class JobFolder(BaseModel):
    """PostsView 顶层的 Job 文件夹视图"""
    job_id: int
    task_id: int
    display_name: Optional[str] = None
    task_name: str
    status: str
    posts_count: int = Field(default=0, description="本次 Job 入库的 Post 数")
    progress_pages: int = 0
    progress_posts: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime


class JobFolderPage(BaseModel):
    items: list[JobFolder]
    total: int
    page: int
    page_size: int


class RecrawlRequest(BaseModel):
    """重新抓取一批 Post 的详情页，回填 cover / post_date 等"""
    post_ids: list[int] = Field(default_factory=list)


class RecrawlResponse(BaseModel):
    updated: int = 0
    failed: int = 0
    items: list[dict] = Field(default_factory=list)


# ============== 智能过滤学习 ==============
class FilterKeywordBase(BaseModel):
    keyword: str = Field(description="关键词（小写、去空）")
    source: str = Field(default="manual", description="manual | learned | user_dislike | user_like")
    weight: float = Field(default=1.0, ge=0.0, le=1.0)


class FilterKeywordRead(FilterKeywordBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    hit_count: int = 0
    created_at: datetime


class FilterKeywordCreate(BaseModel):
    keywords: list[str] = Field(description="批量新增的关键词数组")


class FilterRuleBase(BaseModel):
    name: str = Field(description="规则名")
    scope: str = Field(default="site", description="site | global")
    site_id: Optional[int] = Field(default=None, description="scope=site 时必填")
    rule_type: str = Field(default="exclude", description="exclude | include | tag")
    enabled: bool = True
    note: Optional[str] = None


class FilterRuleCreate(FilterRuleBase):
    keywords: list[str] = Field(default_factory=list, description="初始化关键词")


class FilterRuleUpdate(BaseModel):
    name: Optional[str] = None
    scope: Optional[str] = None
    site_id: Optional[int] = None
    rule_type: Optional[str] = None
    enabled: Optional[bool] = None
    note: Optional[str] = None


class FilterRuleRead(FilterRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    keyword_count: int = 0
    keywords: list[FilterKeywordRead] = Field(default_factory=list)


class FilterRuleSummary(BaseModel):
    """列表用精简字段（不含 keywords 明细）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    scope: str
    site_id: Optional[int] = None
    rule_type: str
    enabled: bool
    note: Optional[str] = None
    keyword_count: int = 0
    hit_count_total: int = 0
    created_at: datetime
    updated_at: datetime


class UserFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: Optional[int]
    site_id: Optional[int]
    title: str
    action: str
    keywords_extracted: list[str] = Field(default_factory=list)
    rule_id: Optional[int] = None
    rule_type: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


class DislikeRequest(BaseModel):
    rule_id: Optional[int] = Field(default=None, description="指定规则 ID；为空则自动找/创建该站点的 default-exclude 规则")


class DislikeResponse(BaseModel):
    ok: bool
    rule_id: int
    rule_name: str
    keywords_added: list[str] = Field(default_factory=list)
    extractor: str = Field(description="ai | local")
    post_deleted: bool = True


# ============== App Settings ==============
class AppSettingRead(BaseModel):
    """前端读取配置。api_key 永远只返回掩码 + 末 4 位，绝不返回明文。"""

    key: str
    value: Optional[str] = None
    masked: bool = Field(default=False, description="是否做了脱敏")
    source: str = Field(description="db | default（db 表示来自 app_settings 表，覆盖默认；default 表示来自 .env 默认值）")
    updated_at: Optional[datetime] = None


class AppSettingUpdate(BaseModel):
    """前端提交配置。value 为空字符串等价于清空（回退到 .env 默认）"""

    value: Optional[str] = None


class AppSettingTestRequest(BaseModel):
    """测试 AI 连接：用当前提交值或 db 现有值去 ping 一下 chat/completions"""

    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout: Optional[int] = None


class AppSettingTestResponse(BaseModel):
    ok: bool
    message: str
    latency_ms: Optional[int] = None
    model_reply: Optional[str] = None


class LikeRequest(BaseModel):
    rule_id: Optional[int] = Field(default=None)


class LikeResponse(BaseModel):
    ok: bool
    rule_id: int
    rule_name: str
    keywords_added: list[str] = Field(default_factory=list)
    extractor: str
    post_deleted: bool = False
