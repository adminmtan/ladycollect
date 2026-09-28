"""采集结果 API：列表/筛选/详情/复制链接/补抓封面"""
from __future__ import annotations

import json
from datetime import date as date_t, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, or_, select

from app.config import settings as app_settings
from app.crawler.browser import make_browser
from app.crawler.runner import _has_age_gate, _select_parsers, _force_browser, fetch_html
from app.db import get_session
from app.models import Job, Post, Site, Task, utcnow
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

        # 决定抓取方式
        if use_browser:
            ctx_factory = lambda: make_browser(
                headless=True,
                humanize=False,
                proxy=proxy,
                user_agent=ua,
                fingerprint_seed=site.fingerprint_seed,
                profile_dir=app_settings.profile_dir,
            )
        else:
            # 1mei 走纯 HTTP 即可（更稳更快）
            from app.crawler.http_client import fetch_html

            ctx_factory = None

        if ctx_factory is not None:
            with ctx_factory() as ctx:
                page = ctx.new_page()
                # 先过 age gate（一次即可）：访问站点首页
                try:
                    page.goto(site.base_url, wait_until="domcontentloaded",
                              timeout=app_settings.default_request_timeout * 1000)
                    page.wait_for_timeout(1500)
                    if _has_age_gate(page):
                        page.locator("a.enter-btn").first.click(timeout=5000)
                        page.wait_for_load_state("domcontentloaded",
                                                 timeout=app_settings.default_request_timeout * 1000)
                        page.wait_for_timeout(1500)
                except Exception:
                    pass

                for p in group:
                    try:
                        page.goto(p.url, wait_until="domcontentloaded",
                                  timeout=app_settings.default_request_timeout * 1000)
                        page.wait_for_timeout(2000)
                        if _has_age_gate(page):
                            page.locator("a.enter-btn").first.click(timeout=5000)
                            page.wait_for_load_state("domcontentloaded",
                                                     timeout=app_settings.default_request_timeout * 1000)
                            page.wait_for_timeout(1500)
                            page.goto(p.url, wait_until="domcontentloaded",
                                      timeout=app_settings.default_request_timeout * 1000)
                            page.wait_for_timeout(2000)
                        html = page.content()
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
        else:
            # 纯 HTTP 路径（1mei）
            for p in group:
                try:
                    html = fetch_html(p.url, headers={"User-Agent": ua},
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
