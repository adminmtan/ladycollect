"""采集结果 API：列表/筛选/详情/复制链接/补抓封面"""
from __future__ import annotations

import json
import time
from datetime import date as date_t, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, or_, select

from app.config import settings as app_settings
from app.crawler.browser import make_page
from app.crawler.runner import _has_age_gate, _select_parsers, _force_browser, fetch_html
from app.db import get_session
from app.learning import get_extractor
from app.models import FilterKeyword, FilterRule, Job, Post, Site, Task, UserFeedback, utcnow
from app.schemas import (
    CopyLinksRequest,
    CopyLinksResponse,
    JobFolder,
    JobFolderPage,
    PostPage,
    PostRead,
    RecrawlRequest,
    RecrawlResponse,
)
from app.api.feedback import (
    _get_or_create_default_rule,
    _persist_keywords,
    _record_feedback,
)
from app.crawler.runner import invalidate_filter_rules_cache

router = APIRouter(prefix="/api/posts", tags=["posts"])


def _to_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        try:
            arr = json.loads(v)
            if isinstance(arr, list):
                return [str(x) for x in arr]
        except Exception:
            pass
    return []


def _collect_all_exclude_keywords(session: Session) -> list[str]:
    """聚合所有 enabled exclude 规则的关键词并集 (去重, 按字母排序)

    用于 curate_preview 的 global mode: 把全站所有站点的过滤关键词聚合展示,
    不创建/不修改任何规则, 仅作为只读候选.
    """
    rules = session.exec(
        select(FilterRule).where(
            FilterRule.enabled == True,  # noqa: E712
            FilterRule.rule_type == "exclude",
        )
    ).all()
    if not rules:
        return []
    rule_ids = [r.id for r in rules]
    rows = session.exec(
        select(FilterKeyword).where(FilterKeyword.rule_id.in_(rule_ids))
    ).all()
    seen: set[str] = set()
    out: list[str] = []
    for k in rows:
        kw = (k.keyword or "").strip().lower()
        if not kw or kw in seen:
            continue
        seen.add(kw)
        out.append(kw)
    out.sort()
    return out


@router.get("", response_model=PostPage)
def list_posts(
    site_id: Optional[int] = None,
    keyword: Optional[str] = None,
    date_from: Optional[date_t] = None,
    date_to: Optional[date_t] = None,
    has_magnet: Optional[bool] = None,
    has_ed2k: Optional[bool] = None,
    job_id: Optional[int] = None,
    # 入库日期筛选（按 Post.created_at）
    created_from: Optional[date_t] = None,
    created_to: Optional[date_t] = None,
    # 排序：created_desc(默认) | created_asc | post_date_desc | post_date_asc
    sort: str = "created_desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=200),
    session: Session = Depends(get_session),
):
    _page = page if isinstance(page, int) else 1
    _page_size = page_size if isinstance(page_size, int) else 24
    q = select(Post)
    if site_id is not None:
        q = q.where(Post.site_id == site_id)
    if job_id is not None:
        q = q.where(Post.job_id == job_id)
    if keyword:
        kw = f"%{keyword}%"
        q = q.where(or_(Post.title.like(kw), Post.summary.like(kw)))
    if date_from:
        q = q.where(Post.post_date >= date_from)
    if date_to:
        q = q.where(Post.post_date <= date_to)
    # 入库日期筛选（创建时间）
    if created_from:
        q = q.where(Post.created_at >= created_from)
    if created_to:
        # created_to 通常传 YYYY-MM-DD，加 1 天作为上界让「包含当天」生效
        from datetime import timedelta as _td
        q = q.where(Post.created_at < (created_to + _td(days=1)))

    # 排序：NULL 字段在 asc/desc 中都排到末尾（Post.post_date 允许 NULL）
    from sqlalchemy import nullslast
    if sort == "created_asc":
        q = q.order_by(Post.created_at.asc(), Post.id.asc())
    elif sort == "post_date_desc":
        q = q.order_by(nullslast(Post.post_date.desc()), Post.id.desc())
    elif sort == "post_date_asc":
        q = q.order_by(nullslast(Post.post_date.asc()), Post.id.asc())
    else:
        # 默认 created_desc
        q = q.order_by(Post.created_at.desc(), Post.id.desc())

    items = session.exec(q).all()

    # 二次过滤：magnet / ed2k 是否存在
    filtered = []
    for p in items:
        mags = _to_list(p.magnet)
        ed2s = _to_list(p.ed2k)
        if has_magnet and not mags:
            continue
        if has_ed2k and not ed2s:
            continue
        # 注入反序列化字段以满足 PostRead
        p.magnet = mags
        p.ed2k = ed2s
        filtered.append(p)

    total = len(filtered)
    start = (_page - 1) * _page_size
    end = start + _page_size
    return PostPage(items=filtered[start:end], total=total, page=_page, page_size=_page_size)


@router.get("/all-ids")
def all_post_ids(
    site_id: Optional[int] = None,
    keyword: Optional[str] = None,
    date_from: Optional[date_t] = None,
    date_to: Optional[date_t] = None,
    has_magnet: Optional[bool] = None,
    has_ed2k: Optional[bool] = None,
    job_id: Optional[int] = None,
    created_from: Optional[date_t] = None,
    created_to: Optional[date_t] = None,
    sort: str = "created_desc",
    session: Session = Depends(get_session),
):
    """按当前筛选条件取「全部 Post id」。用于「复制文本」一键取列表全量链接。

    返回 { ids: [...], total: N }。最多 5000 条，超出截断（前端有提示）。
    """
    from sqlalchemy import nullslast

    q = select(Post.id)
    if site_id is not None:
        q = q.where(Post.site_id == site_id)
    if job_id is not None:
        q = q.where(Post.job_id == job_id)
    if keyword:
        kw = f"%{keyword}%"
        q = q.where(or_(Post.title.like(kw), Post.summary.like(kw)))
    if date_from:
        q = q.where(Post.post_date >= date_from)
    if date_to:
        q = q.where(Post.post_date <= date_to)
    if created_from:
        q = q.where(Post.created_at >= created_from)
    if created_to:
        from datetime import timedelta as _td
        q = q.where(Post.created_at < (created_to + _td(days=1)))

    if sort == "created_asc":
        q = q.order_by(Post.created_at.asc(), Post.id.asc())
    elif sort == "post_date_desc":
        q = q.order_by(nullslast(Post.post_date.desc()), Post.id.desc())
    elif sort == "post_date_asc":
        q = q.order_by(nullslast(Post.post_date.asc()), Post.id.asc())
    else:
        q = q.order_by(Post.created_at.desc(), Post.id.desc())

    ids_all = [int(x) for x in session.exec(q).all()]

    # 二次过滤 magnet/ed2k（与 list_posts 一致）
    if has_magnet or has_ed2k:
        q2 = select(Post.id, Post.magnet, Post.ed2k)
        if site_id is not None:
            q2 = q2.where(Post.site_id == site_id)
        if job_id is not None:
            q2 = q2.where(Post.job_id == job_id)
        rows = session.exec(q2).all()
        ids_all = [
            pid
            for pid, m, e in rows
            if (not has_magnet or _to_list(m))
            and (not has_ed2k or _to_list(e))
        ]

    total = len(ids_all)
    ids = ids_all[:5000]
    return {"ids": ids, "total": total, "truncated": total > len(ids)}


@router.get("/{post_id}", response_model=PostRead)
def get_post(post_id: int, session: Session = Depends(get_session)):
    p = session.get(Post, post_id)
    if not p:
        raise HTTPException(404, "post 不存在")
    p.magnet = _to_list(p.magnet)
    p.ed2k = _to_list(p.ed2k)
    return p


@router.post("/copy-links", response_model=CopyLinksResponse)
def copy_links(payload: CopyLinksRequest, session: Session = Depends(get_session)):
    """按 post_ids 取磁链/电驴链接合并去重"""
    if not payload.post_ids:
        return CopyLinksResponse()

    posts = session.exec(select(Post).where(Post.id.in_(payload.post_ids))).all()
    mags: list[str] = []
    ed2s: list[str] = []
    seen_m: set[str] = set()
    seen_e: set[str] = set()
    for p in posts:
        for m in _to_list(p.magnet):
            if m not in seen_m:
                seen_m.add(m)
                mags.append(m)
        for e in _to_list(p.ed2k):
            if e not in seen_e:
                seen_e.add(e)
                ed2s.append(e)

    result = CopyLinksResponse()
    if "magnet" in payload.kinds:
        result.magnet = mags
    if "ed2k" in payload.kinds:
        result.ed2k = ed2s
    return result


@router.post("/copy-links/text", response_class=PlainTextResponse)
def copy_links_text(payload: CopyLinksRequest, session: Session = Depends(get_session)):
    """直接返回纯文本（一键复制）：magnet / ed2k 按顺序换行拼接"""
    data = copy_links(payload, session)
    lines: list[str] = []
    if "magnet" in payload.kinds:
        lines.extend(data.magnet)
    if "ed2k" in payload.kinds:
        lines.extend(data.ed2k)
    return "\n".join(lines)


@router.delete("/{post_id}")
def delete_post(post_id: int, session: Session = Depends(get_session)):
    p = session.get(Post, post_id)
    if not p:
        raise HTTPException(404, "post 不存在")
    session.delete(p)
    session.commit()
    return {"ok": True}


class DeletePostsBody(BaseModel):
    post_ids: list[int] = Field(default_factory=list)


@router.delete("")
def delete_posts_batch(payload: DeletePostsBody, session: Session = Depends(get_session)):
    """批量删除 Post（按 id 列表）。返回被删数量。

    注意：路径必须放在 DELETE /{post_id} 之前注册（实际 FastAPI 路由按声明顺序匹配，长路径精确优先，
    但 DELETE "" 与 DELETE "/{post_id}" 不冲突；这里额外校验以防 path 误解析）。
    """
    if not payload.post_ids:
        raise HTTPException(400, "post_ids 不能为空")
    if len(payload.post_ids) > 1000:
        raise HTTPException(400, "单次最多 1000 条")
    posts = session.exec(select(Post).where(Post.id.in_(payload.post_ids))).all()
    cnt = 0
    for p in posts:
        session.delete(p)
        cnt += 1
    session.commit()
    return {"ok": True, "deleted": cnt}


@router.get("/jobs/folders", response_model=JobFolderPage)
def list_job_folders(
    site_id: Optional[int] = None,
    task_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
):
    """PostsView 顶层展示：每个 Job 一个文件夹（仅含入库了帖子的 Job）。

    设计：采集结果页是「帖子归集」视图，没有帖子入库的 Job 不应出现在这里——
    包括 failed Job 和「完成但全被关键词过滤掉」的 Job。
    """
    _page = page if isinstance(page, int) else 1
    _page_size = page_size if isinstance(page_size, int) else 50

    # 1) 一次 SQL 拿到「有帖子入库」的 Job（EXISTS 子查询过滤），同时拿到 posts_count。
    #    这样不管 Python 进程内存里跑的是哪一版代码（重启前/后），过滤都生效。
    posts_subq = (
        select(Post.job_id, func.count(Post.id).label("cnt"))
        .where(Post.job_id.is_not(None))
        .group_by(Post.job_id)
        .subquery()
    )
    jq = (
        select(Job, Task.name, posts_subq.c.cnt)
        .join(Task, Task.id == Job.task_id)
        .join(posts_subq, posts_subq.c.job_id == Job.id)
        .where(posts_subq.c.cnt > 0)
    )
    if site_id is not None:
        jq = jq.where(Task.site_id == site_id)
    if task_id is not None:
        jq = jq.where(Job.task_id == task_id)
    rows = session.exec(jq.order_by(Job.id.desc())).all()
    if not rows:
        return JobFolderPage(items=[], total=0, page=_page, page_size=_page_size)

    folders = [
        JobFolder(
            job_id=j.id,
            task_id=j.task_id,
            display_name=j.display_name,
            task_name=tname,
            status=j.status,
            posts_count=int(cnt or 0),
            progress_pages=j.progress_pages or 0,
            progress_posts=j.progress_posts or 0,
            error=j.error,
            started_at=j.started_at,
            finished_at=j.finished_at,
            created_at=j.created_at,
        )
        for j, tname, cnt in rows
    ]
    folders.sort(key=lambda f: -f.created_at.timestamp())

    total = len(folders)
    start = (_page - 1) * _page_size
    end = start + _page_size
    return JobFolderPage(items=folders[start:end], total=total, page=_page, page_size=_page_size)


@router.delete("/jobs/{job_id}")
def delete_job_folder(job_id: int, session: Session = Depends(get_session)):
    """删除一个 JobFolder：Job 本身删除，Post 保留（job_id 置 NULL）。

    设计原则：Posts 是独立的采集结果，不属于任何 Job/Task 的生命周期。
    删 JobFolder 只删「Job 运行记录」本身，posts 表数据保留，job_id 置 NULL。
    """
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job 不存在")

    # 1) 把该 Job 下的 Post 解绑（job_id 置 NULL），而不是删除
    from sqlalchemy import update as _update
    session.exec(
        _update(Post).where(Post.job_id == job_id).values(job_id=None)
    )

    # 2) 删 Job 本身
    session.delete(job)
    session.commit()
    return {
        "ok": True,
        "deleted_job": job_id,
        "orphaned_posts": "posts 保留，job_id 已置 NULL",
    }


@router.post("/recrawl", response_model=RecrawlResponse)
def recrawl_posts(payload: RecrawlRequest, session: Session = Depends(get_session)):
    """重新访问一批 Post 的详情页，回填 cover / post_date / magnet / ed2k / author / title。

    用途：之前入库时 cover 解析失败或代码未带 cover 的旧数据，可用此接口一次性补抓。

    行为：
      - 同步串行执行（避免给目标站点造成瞬时压力），每个 post 单独 goto + 解析
      - 命中年龄验证门（Discuz 站）时点击通过
      - 只有「实际变了」或「原本为空」的字段会被回填，不会覆盖已有非空值
        （cover / post_date / author / title / magnet / ed2k 都按此策略）
    """
    ids = [int(x) for x in (payload.post_ids or []) if x is not None]
    if not ids:
        raise HTTPException(400, "post_ids 不能为空")
    if len(ids) > 500:
        raise HTTPException(400, "单次最多 500 条")

    posts = session.exec(select(Post).where(Post.id.in_(ids))).all()
    if not posts:
        return RecrawlResponse(updated=0, failed=0, items=[])

    # 按 site 分组，同一站点复用同一个 browser context 和同一个 adapter
    by_site: dict[int, list[Post]] = {}
    for p in posts:
        by_site.setdefault(p.site_id, []).append(p)

    updated = 0
    failed = 0
    items: list[dict] = []

    for site_id, group in by_site.items():
        site = session.get(Site, site_id)
        if not site:
            failed += len(group)
            for p in group:
                items.append({"post_id": p.id, "ok": False, "reason": "site 不存在"})
            continue

        list_parser, detail_parser = _select_parsers(site)
        use_browser = _force_browser(site)
        proxy = site.proxy or app_settings.proxy_url
        ua = site.user_agent or app_settings.default_user_agent

        if use_browser:
            ctx_factory = lambda: make_page(
                headless=True,
                proxy=proxy,
                user_agent=ua,
                profile_dir=app_settings.profile_dir,
            )
        else:
            from app.crawler.http_client import fetch_html
            ctx_factory = None

        if ctx_factory is not None:
            with ctx_factory() as page:
                try:
                    page.get(site.base_url, timeout=app_settings.default_request_timeout)
                    time.sleep(1.5)
                    if _has_age_gate(page):
                        btn = page.raw.ele("css:a.enter-btn")
                        if btn:
                            btn.click()
                            time.sleep(2)
                except Exception:
                    pass

                for p in group:
                    try:
                        page.get(p.url, timeout=app_settings.default_request_timeout)
                        time.sleep(2)
                        if _has_age_gate(page):
                            btn = page.raw.ele("css:a.enter-btn")
                            if btn:
                                btn.click()
                                time.sleep(2)
                            page.get(p.url, timeout=app_settings.default_request_timeout)
                            time.sleep(2)
                        detail_html = page.html
                        detail = detail_parser(detail_html, site.base_url)

                        changed = _apply_detail(p, detail)
                        if changed:
                            p.updated_at = utcnow()
                            session.add(p)
                            updated += 1
                        items.append({
                            "post_id": p.id,
                            "ok": True,
                            "cover": p.cover,
                            "post_date": str(p.post_date) if p.post_date else None,
                            "magnet": len(p.magnet or []),
                            "ed2k": len(p.ed2k or []),
                            "changed": changed,
                        })
                    except Exception as e:
                        failed += 1
                        items.append({"post_id": p.id, "ok": False, "reason": str(e)[:200]})
        else:
            from app.crawler.http_client import fetch_html as _fetch
            for p in group:
                try:
                    html = _fetch(p.url, headers={"User-Agent": ua},
                                  timeout=app_settings.default_request_timeout)
                    detail = detail_parser(html, site.base_url)

                    changed = _apply_detail(p, detail)
                    if changed:
                        p.updated_at = utcnow()
                        session.add(p)
                        updated += 1
                    items.append({
                        "post_id": p.id,
                        "ok": True,
                        "cover": p.cover,
                        "post_date": str(p.post_date) if p.post_date else None,
                        "magnet": len(p.magnet or []),
                        "ed2k": len(p.ed2k or []),
                        "changed": changed,
                    })
                except Exception as e:
                    failed += 1
                    items.append({"post_id": p.id, "ok": False, "reason": str(e)[:200]})

    session.commit()
    return RecrawlResponse(updated=updated, failed=failed, items=items)


def _apply_detail(p: Post, detail) -> bool:
    """回填到 Post：只在「原值空」或「新值非空且不同」时覆盖。返回 True 表示有字段变更。"""
    changed = False
    if detail.title and detail.title != p.title:
        p.title = detail.title; changed = True
    if detail.author and (not p.author):
        p.author = detail.author; changed = True
    if detail.cover and detail.cover != p.cover:
        p.cover = detail.cover; changed = True
    if detail.post_date and (not p.post_date):
        p.post_date = detail.post_date; changed = True
    # magnet / ed2k：原值为空时用 detail，否则保留更长的那一份
    dm = list(detail.magnet or [])
    de = list(detail.ed2k or [])
    if dm and not _to_list(p.magnet):
        p.magnet = dm; changed = True
    if de and not _to_list(p.ed2k):
        p.ed2k = de; changed = True
    return changed


# ============== 智能整理（AI 拆解关键词 + 手动确认 + 批量删除） ==============

class CuratePreviewRequest(BaseModel):
    """智能整理预览：传一组 post id，调 AI 拆解关键词，并预览「哪些 post 会被命中」。

    工作流：
    1. 用户勾选若干条帖子（或不勾选 → 当前筛选条件下的所有帖子）
    2. 调本接口 → AI 拆解关键词 + 列出每个关键词会影响哪些帖子
    3. 前端弹窗展示，用户编辑/删除/新增关键词、勾选要删除的 post
    4. 用户点确认 → 调 /curate/commit
    """
    # 场景 A: 站点级 (不传 post_ids, 传 site_id) -> 候选 = 该站点过滤规则已存在关键词
    # 场景 B: 单帖 dislike (传 1 个 post_id) -> 候选 = AI 对该帖子输出的关键词
    # 场景 C: 多帖批量 (传多个 post_ids) -> 候选 = AI 对这些帖子输出的关键词 (合并去重)
    post_ids: list[int] = Field(default_factory=list, description="要整理的 post id 列表")
    site_id: Optional[int] = Field(default=None, description="备选：站点级批量整理")
    top_n: int = Field(default=10, ge=3, le=20, description="AI 返回几个关键词")


class AffectedPost(BaseModel):
    post_id: int
    title: str
    site_id: int
    matched_keywords: list[str] = Field(default_factory=list)


class CuratePreviewResponse(BaseModel):
    ok: bool = True
    mode: str = Field(description="site | single | multi | global  场景标识")
    extractor: str = Field(description="ai | local")
    suggested_rule_id: int
    suggested_rule_name: str
    read_only: bool = Field(default=False, description="True 表示前端禁用 commit 按钮 (global 模式只读聚合)")
    # AI 这次新生成的关键词（仅在 single / multi 场景有效；site/global 场景为 []）
    ai_keywords: list[str] = Field(default_factory=list, description="AI 本次新增建议的关键词")
    # 合并后的最终关键词集合（已存在的 + AI 新增去重），前端初始编辑态
    suggested_keywords: list[str] = Field(default_factory=list, description="已合并的最终关键词（含历史规则 + AI 建议）")
    # 已存在的关键词（标记为「历史」关键词，不可直接删除除非用户主动删）
    existing_keywords: list[str] = Field(default_factory=list, description="规则里已存在的关键词")
    affected: list[AffectedPost] = Field(default_factory=list)
    unmatched_count: int = 0
    total_titles: int
    # 候选帖子全集 (single/multi 模式 = 同站点前 100 条; site 模式 = 同站点全部前 200 条)
    # 前端用这个集合做 originalPosts, 手动加关键词后能正确从全集里筛受影响
    pool: list[AffectedPost] = Field(default_factory=list)


class CurateCommitRequest(BaseModel):
    """用户确认后批量入库 + 删除

    keywords = 用户当前弹窗里最终保留的关键词全集
    previous_existing = 弹窗打开时该规则已有的关键词, 用于计算哪些已被用户在前端删除
    """
    rule_id: int = Field(description="要写入关键词的 filter_rule id")
    keywords: list[str] = Field(description="用户最终保留的关键词列表（合并视图的最终态）")
    previous_existing: list[str] = Field(
        default_factory=list,
        description="弹窗打开时规则已存在的关键词，用于识别哪些已被用户删除",
    )
    post_ids_to_delete: list[int] = Field(default_factory=list, description="要被批量删除的 post id 列表")
    note: Optional[str] = Field(default=None, description="可选备注，记录到 user_feedback")


class CurateCommitResponse(BaseModel):
    ok: bool
    keywords_added: list[str] = Field(default_factory=list)
    keywords_existing: list[str] = Field(default_factory=list)
    keywords_removed: list[str] = Field(default_factory=list, description="本次被用户从规则里移除的关键词")
    posts_deleted: int = 0
    rule_id: int
    rule_name: str


@router.post("/curate/preview", response_model=CuratePreviewResponse)
def curate_preview(payload: CuratePreviewRequest, session: Session = Depends(get_session)) -> CuratePreviewResponse:
    """智能整理预览: 只读, 不删数据

    四种 mode:
    - site:   站点级批量 (传 site_id) -> 候选 = 该站点默认 exclude 规则的当前关键词
    - single: 单帖 dislike (传 1 个 post_id) -> 候选 = AI 对该帖输出的关键词
    - multi:  多帖批量 (传多个 post_ids) -> 候选 = AI 对这些帖输出的关键词 (合并去重)
    - global: 全局整理 (都不传) -> 候选 = 所有 enabled exclude 规则的关键词并集 (只读聚合展示)

    候选关键词编辑语义:
    - site:           候选 = 该规则已存在的关键词, 用户增删会写回这条规则
    - global:         候选 = 所有规则的关键词并集 (只读聚合, 编辑只影响全局 default rule)
    - single / multi: 候选 = AI 对这些帖子输出的新关键词 (不含已存在)

    注意: global 模式不会主动创建新规则, 只是聚合展示所有 exclude 规则的关键词供查看.
    """
    post_ids = payload.post_ids or []
    has_posts = len(post_ids) > 0
    has_site = payload.site_id is not None

    # 0) 先确定 mode
    # 优先级: post_ids 长度决定 single/multi, 否则 site_id 决定 site, 都没传 -> global
    if has_posts and len(post_ids) == 1:
        mode = "single"
    elif has_posts and len(post_ids) > 1:
        mode = "multi"
    elif has_site:
        mode = "site"
    else:
        mode = "global"

    # 1) 取 post 列表 (single/multi/site 需要)
    if has_posts:
        posts = session.exec(select(Post).where(Post.id.in_(post_ids))).all()
        if not posts:
            raise HTTPException(404, "未找到任何 post")
        primary_site_id = posts[0].site_id
        site_ids = list({p.site_id for p in posts})
    elif mode == "site":
        primary_site_id = payload.site_id
        site_ids = [primary_site_id]
        posts = session.exec(
            select(Post).where(Post.site_id == primary_site_id)
            .order_by(Post.created_at.desc()).limit(200)
        ).all()
    else:
        # global 模式: 不取 post, 只是管理关键词
        primary_site_id = None
        site_ids = []
        posts = []

    # 2) 取「要管理的关键词」 (global 模式不走 _get_or_create_default_rule, 不会创建任何规则)
    if mode == "global":
        # ★ global 模式: 候选 = 所有 enabled exclude 规则的关键词并集 (去重, 字母排序)
        # 只读聚合展示, 不创建/不修改任何规则
        existing_keywords = _collect_all_exclude_keywords(session)
        rule_id = 0  # sentinel: 前端 commit 时识别为全局聚合模式
        rule_name = "全站过滤关键词聚合"
    else:
        # 找/建一个站点默认 exclude 规则
        rule = _get_or_create_default_rule(
            session,
            site_id=primary_site_id,
            rule_type="exclude",
            rule_name_prefix="智能整理 exclude",
        )
        rule_id = rule.id
        rule_name = rule.name
        existing_kw_rows = session.exec(
            select(FilterKeyword).where(FilterKeyword.rule_id == rule.id)
        ).all()
        existing_keywords = [k.keyword for k in existing_kw_rows]

    existing_set = {k.lower() for k in existing_keywords}

    # 4) 按 mode 决定「候选关键词」来源
    ai_keywords_new: list[str] = []
    extractor = get_extractor()
    source = "local"

    if mode in ("site", "global"):
        # ★ 站点级 / 全局级整理：候选关键词 = 现有过滤关键词，不混入 AI 建议
        merged_keywords = list(existing_keywords)
        ai_keywords_new = []
        source = "local"
    else:
        # single / multi：候选关键词 = AI 对这些帖子输出的关键词
        titles = [p.title or "" for p in posts if p.title]
        # 辅助信号：该站点的 dislike 历史标题（让 AI 学习偏好）
        # 注意: single 模式 (1 个 post) 不带历史, 让 AI 专注分析这一条帖子;
        # multi 模式 (多条) 才带历史学偏好. 否则当前帖子的关键词会被历史噪声淹没.
        history_titles: list[str] = []
        if mode == "multi" and len(site_ids) >= 1:
            if len(site_ids) == 1:
                sid = site_ids[0]
                for fb in session.exec(
                    select(UserFeedback)
                    .where(
                        UserFeedback.site_id == sid,
                        UserFeedback.action == "dislike",
                    )
                    .order_by(UserFeedback.id.desc())
                    .limit(15)
                ).all():
                    if fb.title and fb.title not in history_titles:
                        history_titles.append(fb.title)
            else:
                per_site = max(3, 15 // len(site_ids))
                for sid in site_ids:
                    for fb in session.exec(
                        select(UserFeedback)
                        .where(UserFeedback.site_id == sid, UserFeedback.action == "dislike")
                        .order_by(UserFeedback.id.desc())
                        .limit(per_site)
                    ).all():
                        if fb.title and fb.title not in history_titles:
                            history_titles.append(fb.title)

        titles_for_ai = list({*titles, *history_titles})[:20]
        keywords, source = extractor.extract(titles_for_ai, action="dislike", top_n=payload.top_n)
        ai_keywords_raw = [k.strip().lower() for k in (keywords or []) if k and k.strip()]
        ai_keywords_new = [k for k in ai_keywords_raw if k and k not in existing_set]
        # ★ 关键: single/multi 模式下, merged_keywords 只取 ai_keywords_new,
        # existing_keywords 保留在独立字段作为参考, 但不进入编辑区
        # 这样单帖 dislike 弹窗里只会看到 AI 给该帖的关键词, 不会被历史词干扰
        merged_keywords = list(ai_keywords_new)

    # 5) 用「合并后的关键词」去匹配每个 post，列出受影响帖子
    # 在 single/multi 模式下, posts 已经是用户传进来的; 在 site 模式下是站点前 200 条
    # 但对于 single 模式 (用户传了 1 个 post_id), 用户期望「加一个关键词后, 站点里其它包含该词的帖子也显示」
    # 所以这里要按 site_id 扩出去, 让 affected 反映「真正会被这些关键词命中的帖子」, 而不只是用户选的那条
    affected: list[AffectedPost] = []
    unmatched = 0

    # 按需扩展 post 池 (single/multi 模式): 用 site_ids 内每个站点的前 100 条帖子
    pool: list = list(posts)
    if mode in ("single", "multi"):
        site_pool: dict[int, list] = {}
        for sid in site_ids:
            extra = session.exec(
                select(Post).where(Post.site_id == sid)
                .order_by(Post.created_at.desc()).limit(100)
            ).all()
            site_pool[sid] = extra
        # 保留用户传的原 posts (置顶), 再追加同站点其它帖子去重
        seen_pids = {p.id for p in pool}
        for sid, extras in site_pool.items():
            for ep in extras:
                if ep.id not in seen_pids:
                    pool.append(ep)
                    seen_pids.add(ep.id)

    for p in pool:
        t_lc = (p.title or "").lower()
        hits = [k for k in merged_keywords if k and k in t_lc]
        if hits:
            affected.append(
                AffectedPost(
                    post_id=p.id,
                    title=p.title or "",
                    site_id=p.site_id,
                    matched_keywords=hits,
                )
            )
        else:
            unmatched += 1

    session.commit()
    if mode != "global":
        # global 模式下没有具体 rule 可刷新, rule 变量未定义
        session.refresh(rule)

    return CuratePreviewResponse(
        ok=True,
        mode=mode,
        extractor=source,
        suggested_rule_id=rule_id,
        suggested_rule_name=rule_name,
        read_only=(mode == "global"),
        ai_keywords=ai_keywords_new,
        suggested_keywords=merged_keywords,
        existing_keywords=existing_keywords,
        affected=affected,
        unmatched_count=unmatched,
        total_titles=len(pool),
        # 全集 (含未命中的) 传给前端, 让前端 manual add kw 时能从全 pool 重算 affected
        pool=[
            AffectedPost(
                post_id=p.id,
                title=p.title or "",
                site_id=p.site_id,
                matched_keywords=[],  # 前端会用 workingKeywords 自己重算
            )
            for p in pool
        ],
    )


@router.post("/curate/commit", response_model=CurateCommitResponse)
def curate_commit(payload: CurateCommitRequest, session: Session = Depends(get_session)):
    """用户确认后批量入库关键词 + 删除匹配到的帖子

    行为:
      - keywords 中不在 previous_existing 的 -> 新增 (source=user_dislike)
      - previous_existing 中不在 keywords 的 -> 物理删除 (用户在前端移除了)
      - keywords 交 previous_existing 的 -> 保留不动
    """
    rule = session.get(FilterRule, payload.rule_id)
    if not rule:
        raise HTTPException(404, "rule 不存在")
    if rule.rule_type != "exclude":
        raise HTTPException(400, "智能整理只支持 exclude 规则")

    # 1) 计算要新增 / 删除的关键词
    previous_set = {k.strip().lower() for k in (payload.previous_existing or []) if k and k.strip()}
    final_set = {k.strip().lower() for k in (payload.keywords or []) if k and k.strip()}
    to_add = sorted(final_set - previous_set)
    # ★ dislike 语义：用户没机会编辑历史词，强制只追加、不删历史词
    # （避免 "+1 −1" 反复替换 bug，见 2026-10-02 测试 test_curate_commit_dislike.py）
    if (payload.note or "").lower() == "dislike":
        to_remove = []
    else:
        to_remove = sorted(previous_set - final_set)

    # 2) 新增关键词入库
    added = _persist_keywords(
        session, rule_id=rule.id, keywords=to_add, source="user_dislike"
    )

    # 3) 删除用户在前端移除的关键词（物理删除）
    removed: list[str] = []
    if to_remove:
        rows = session.exec(
            select(FilterKeyword).where(
                FilterKeyword.rule_id == rule.id,
                FilterKeyword.keyword.in_(to_remove),
            )
        ).all()
        for r in rows:
            removed.append(r.keyword)
            session.delete(r)

    # 4) 写 user_feedback 汇总（一次整理记一条）
    if payload.post_ids_to_delete:
        posts = session.exec(
            select(Post).where(Post.id.in_(payload.post_ids_to_delete))
        ).all()
        for p in posts:
            _record_feedback(
                session,
                post=p,
                title=p.title or "",
                site_id=p.site_id,
                action="dislike",
                keywords=sorted(final_set),
                rule_id=rule.id,
                rule_type="exclude",
                note=(
                    f"批量整理（{payload.note or 'curate'}）· "
                    f"共 {len(posts)} 条 · +{len(added)}/{-len(removed)} 关键词"
                ),
            )

    # 5) 删除指定 posts
    deleted = 0
    if payload.post_ids_to_delete:
        to_del = session.exec(
            select(Post).where(Post.id.in_(payload.post_ids_to_delete))
        ).all()
        for p in to_del:
            session.delete(p)
            deleted += 1

    session.commit()
    session.refresh(rule)

    # 6) 失效缓存
    if rule.scope == "global":
        invalidate_filter_rules_cache(None)
    elif rule.site_id is not None:
        invalidate_filter_rules_cache(rule.site_id)

    return CurateCommitResponse(
        ok=True,
        keywords_added=added,
        keywords_existing=sorted(final_set & previous_set),
        keywords_removed=removed,
        posts_deleted=deleted,
        rule_id=rule.id,
        rule_name=rule.name,
    )
