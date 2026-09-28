"""数据库 ORM 模型"""
from __future__ import annotations

from datetime import datetime, date as date_t
from typing import Optional

from sqlalchemy import Column, DateTime, JSON, UniqueConstraint, Float, Integer, ForeignKey, Boolean
from sqlmodel import Field, SQLModel, Relationship


def utcnow() -> datetime:
    return datetime.utcnow()


# ============== 站点 ==============
class Site(SQLModel, table=True):
    """采集目标站点（域名等可配置）"""

    __tablename__ = "sites"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, description="站点显示名")
    host: str = Field(index=True, description="主域，例如 1mei.live")
    base_url: str = Field(description="完整 base URL，例如 https://1mei.live")
    user_agent: Optional[str] = Field(default=None, description="覆盖默认 UA")
    cookies: Optional[str] = Field(default=None, description="JSON 字符串：[{name, value, domain, path}]")
    proxy: Optional[str] = Field(default=None, description="代理 URL，覆盖全局 proxy")
    fingerprint_seed: Optional[int] = Field(default=None, description="CloakBrowser fingerprint seed")
    # 适配器选择：onemei（默认，WP 主题）/ sehuatang（Discuz! X3.4 论坛）
    adapter: Optional[str] = Field(
        default="onemei",
        description="采集适配器：onemei | sehuatang",
    )
    # 色花堂等 forum 站点专属：板块 FID
    forum_fid: Optional[str] = Field(
        default=None,
        description="Discuz 论坛板块 FID（sehutang 等）。为空则走 list_urls。",
    )
    # 自定义 URL 列表（每个站点独占）。非空则按 URL 直接采集，忽略 forum_fid 与全局 list_all 类逻辑。
    list_urls: Optional[list[str]] = Field(
        default=None,
        sa_column=Column("list_urls", JSON, default=list),
        description="自定义列表 URL 列表。每行一个 URL，或 JSON 数组。非空时忽略 forum_fid。",
    )
    # 标题过滤关键词（站点级，对所有 Task 生效；task 级 keyword 会被合并到 include）
    title_include_keywords: Optional[list[str]] = Field(
        default=None,
        sa_column=Column("title_include_keywords", JSON, default=list),
        description="仅保留标题包含任一关键词的帖子；空表示不过滤",
    )
    title_exclude_keywords: Optional[list[str]] = Field(
        default=None,
        sa_column=Column("title_exclude_keywords", JSON, default=list),
        description="标题包含任一关键词则丢弃；优先级高于 include",
    )
    enabled: bool = Field(default=True)
    note: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow, onupdate=utcnow))


# ============== 任务 ==============
class Task(SQLModel, table=True):
    """一次采集任务的配置"""

    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    # 旧字段：保留兼容（nullable）。新架构使用 site_ids。
    site_id: Optional[int] = Field(default=None, foreign_key="sites.id", index=True)
    # 多站点支持：JSON 数组。一个 task 可对多个 site 同时采集。
    site_ids: Optional[str] = Field(
        default=None,
        sa_column=Column("site_ids", JSON, default=list),
        description="要采集的站点 ID 列表（JSON 数组）。新架构主用此字段。",
    )
    name: str
    kind: str = Field(description="list_all | list_search | list_date | list_category")
    keyword: Optional[str] = Field(default=None, description="搜索关键字（仅 search）")
    date_from: Optional[date_t] = Field(default=None)
    date_to: Optional[date_t] = Field(default=None)
    category: Optional[str] = Field(default=None, description="分类 slug")
    max_pages: int = Field(default=20)
    max_concurrent: int = Field(default=3)
    only_with_links: bool = Field(default=True, description="只保留含 magnet/ed2k 的帖子")
    # 调度：APScheduler cron 表达式（5 或 6 字段）。空表示不启用。
    cron: Optional[str] = Field(default=None, description="Cron 表达式，例如 '0 3 * * *' 表示每天 03:00")
    schedule_enabled: bool = Field(default=False, description="是否启用定时采集")
    # Job 名模板：支持占位符 {date}=YYYY-MM-DD, {ymd}=YYYYMMDD, {task}=task.name
    # 默认 "{task} {ymd}"，调度执行时自动按当日替换
    name_template: Optional[str] = Field(default=None, description="Job 名模板，占位符 {date}/{ymd}/{task}")
    status: str = Field(default="pending", description="pending|running|done|failed")
    next_run_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime, nullable=True))
    last_run_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime, nullable=True))
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow))


class Job(SQLModel, table=True):
    """一次任务执行实例（Task 可被多次执行）"""

    __tablename__ = "jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", index=True)
    display_name: Optional[str] = Field(default=None, index=True, description="调度生成的展示名，如 '每日福利 20260913'")
    status: str = Field(default="pending")  # pending | running | done | failed | cancelled
    progress_pages: int = Field(default=0)
    progress_posts: int = Field(default=0)
    posts_saved: int = Field(default=0)
    error: Optional[str] = Field(default=None)
    log: str = Field(default="", sa_column=Column("log", JSON, default=list))
    started_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime, nullable=True))
    finished_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime, nullable=True))
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow))


# ============== 采集结果 ==============
class Post(SQLModel, table=True):
    """一条帖子（采集入库结果）"""

    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("site_id", "slug", name="uq_posts_site_slug"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="sites.id", index=True)
    task_id: Optional[int] = Field(default=None, foreign_key="tasks.id", index=True)
    job_id: Optional[int] = Field(default=None, foreign_key="jobs.id", index=True)

    post_id: int = Field(index=True, description="目标站自身的文章 ID（URL 中的数字）")
    slug: str = Field(index=True, description="URL slug，去除 host 与数字 ID 的尾段")
    url: str = Field(unique=False, index=True)

    title: str = Field(index=True)
    author: Optional[str] = Field(default=None)
    post_date: Optional[date_t] = Field(default=None, index=True)
    cover: Optional[str] = Field(default=None, description="封面图 URL")
    summary: Optional[str] = Field(default=None)

    magnet: Optional[str] = Field(default=None, sa_column=Column("magnet", JSON, default=list))
    ed2k: Optional[str] = Field(default=None, sa_column=Column("ed2k", JSON, default=list))

    raw: Optional[str] = Field(default=None, sa_column=Column("raw", JSON, default=dict))
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow, onupdate=utcnow))


# ============== 设置 KV ==============
class Setting(SQLModel, table=True):
    """应用级 KV 设置（单条/少条）"""

    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: Optional[str] = Field(default=None)
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow, onupdate=utcnow))


# ============== 智能过滤学习 ==============
class FilterRule(SQLModel, table=True):
    """用户自定义过滤规则（独立于 Site.title_*_keywords，优先级更高）"""

    __tablename__ = "filter_rules"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, description="规则展示名，例如「我的色花堂 exclude」")
    # scope: site=站点级 | global=全局级
    scope: str = Field(default="site", index=True, description="site | global")
    site_id: Optional[int] = Field(
        default=None,
        foreign_key="sites.id",
        index=True,
        description="scope=site 时指向 sites.id；scope=global 时为空",
    )
    # rule_type: exclude=不含（命中丢弃）| include=仅含 | tag=标签分类
    rule_type: str = Field(default="exclude", index=True, description="exclude | include | tag")
    enabled: bool = Field(default=True, description="启停开关")
    note: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow, onupdate=utcnow))


class FilterKeyword(SQLModel, table=True):
    """过滤规则下的关键词集合"""

    __tablename__ = "filter_keywords"

    id: Optional[int] = Field(default=None, primary_key=True)
    rule_id: int = Field(foreign_key="filter_rules.id", index=True)
    # 已 lowercase 去空
    keyword: str = Field(index=True, description="关键词（小写）")
    # 来源：manual=手动 | learned=AI 学习 | user_dislike=用户不喜欢归类 | user_like=用户喜欢归类
    source: str = Field(default="manual", description="manual | learned | user_dislike | user_like")
    weight: float = Field(default=1.0, sa_column=Column(Float, default=1.0), description="权重/置信度 0-1")
    hit_count: int = Field(default=0, sa_column=Column(Integer, default=0), description="命中次数统计")
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow))


class UserFeedback(SQLModel, table=True):
    """用户反馈原始记录（审计 + 学习数据）"""

    __tablename__ = "user_feedback"

    id: Optional[int] = Field(default=None, primary_key=True)
    post_id: Optional[int] = Field(default=None, foreign_key="posts.id", index=True)
    site_id: Optional[int] = Field(default=None, foreign_key="sites.id", index=True)
    title: str = Field(description="被标记的帖子标题")
    # dislike / like
    action: str = Field(index=True, description="dislike | like")
    # AI 提取的关键词（JSON 数组字符串）
    keywords_extracted: Optional[str] = Field(
        default=None,
        sa_column=Column("keywords_extracted", JSON, default=list),
        description="AI/本地规则提取出的关键词",
    )
    rule_id: Optional[int] = Field(default=None, foreign_key="filter_rules.id")
    rule_type: Optional[str] = Field(default=None, description="归类到的规则类型")
    note: Optional[str] = Field(default=None, description="标记备注或失败原因")
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow))


# ============== 应用级运行时配置 ==============
class AppSetting(SQLModel, table=True):
    """key/value 形式的运行时配置（持久化到数据库，优先级高于 .env）

    当前用途：AI 关键词提取的 OpenAI 兼容 API 配置。
    """

    __tablename__ = "app_settings"

    key: str = Field(primary_key=True, description="配置键，例如 openai_api_key")
    value: Optional[str] = Field(default=None, description="配置值（统一以字符串存储）")
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow, onupdate=utcnow))


# ============== 用户认证 ==============
class User(SQLModel, table=True):
    """登录用户（目前是单用户模型：admin only）

    password_hash 用 bcrypt 存。首次启动由 docker-entrypoint.sh 生成强随机密码并打印到日志。
    """

    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, description="登录用户名，默认 admin")
    password_hash: str = Field(description="bcrypt 哈希值")
    role: str = Field(default="admin", description="admin | user（目前总是 admin）")
    # 是否要求首次登录后改密码。前端可基于此提示。
    must_change_password: bool = Field(default=True)
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow))
    updated_at: datetime = Field(default_factory=utcnow, sa_column=Column(DateTime, default=utcnow, onupdate=utcnow))
