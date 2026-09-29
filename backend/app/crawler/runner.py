"""采集执行入口

流程：
1. 用 CloakBrowser 启动一个持久化 context（生产环境）
   或用 httpx 直抓 HTML（本地无浏览器栈时 fallback）
2. 按 list URL 逐个访问，解析 article.excerpt
3. 每篇文章打开详情页，抽取 magnet/ed2k
4. 写入 Post 表（按 (site_id, slug) 唯一）

支持进度回调 / 日志追加 / 失败重试。
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime
from typing import Callable, Optional

import httpx
from sqlmodel import Session, select

from app.config import settings as app_settings
from app.crawler import onemei, sehuatang
from app.crawler.browser import make_browser
from app.crawler.onemei import ListSpec
from app.crawler.parser import (
    parse_detail_html,
    parse_discuz_detail_html,
    parse_discuz_list_html,
    parse_list_html,
)
from app.models import Job, Post, Site, Task, utcnow

logger = logging.getLogger(__name__)


ProgressCB = Callable[[dict], None]


# 全局任务取消注册表：{job_id: threading.Event}
# 由 API 层（stop_job）set，由 runner 循环检查 is_set()
_cancel_events: dict[int, threading.Event] = {}
_cancel_lock = threading.Lock()


def _get_cancel_event(job_id: int) -> threading.Event:
    with _cancel_lock:
        ev = _cancel_events.get(job_id)
        if ev is None:
            ev = threading.Event()
            _cancel_events[job_id] = ev
        return ev


def _clear_cancel_event(job_id: int) -> None:
    with _cancel_lock:
        _cancel_events.pop(job_id, None)


def request_cancel_job(job_id: int) -> bool:
    """外部请求取消一个 Job。返回 True 表示已发出取消信号。"""
    with _cancel_lock:
        ev = _cancel_events.get(job_id)
        if ev is None:
            return False
        ev.set()
        return True


class JobCancelled(Exception):
    """用户主动取消时抛出"""


# 共享 httpx 客户端（线程级单例，连接复用）
_http_client: Optional[httpx.Client] = None


def _http() -> httpx.Client:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(
            timeout=app_settings.default_request_timeout,
            follow_redirects=True,
            headers={"User-Agent": app_settings.default_user_agent},
        )
    return _http_client


def fetch_html(url: str, headers: Optional[dict] = None) -> str:
    """直接用 httpx 抓 HTML（无浏览器 fallback）"""
    client = _http()
    r = client.get(url, headers=headers or {})
    r.raise_for_status()
    if r.encoding and r.encoding.lower() not in ("iso-8859-1", "ascii"):
        return r.text
    return r.content.decode("utf-8", errors="replace")


def _append_log(job: Job, msg: str, session: Session) -> None:
    from datetime import datetime as _dt

    log = list(job.log) if isinstance(job.log, list) else []
    log.append({"ts": _dt.utcnow().isoformat(), "msg": msg})
    job.log = log[-500:]
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(job, "log")
    session.add(job)
    session.commit()


def _log_progress(job_id: int, msg: str, level: int = logging.INFO) -> None:
    """往 crawler.log 写一条带 job_id 前缀的进度日志。

    行为：
    - 一律写入 logger（stderr + ./data/logs/crawler.log）
    - 失败/异常可传 level=logging.WARNING/ERROR/EXCEPTION
    - 不阻塞数据库；日志量很大时不会拖慢采集
    """
    prefix = f"[job={job_id}]"
    logger.log(level, "%s %s", prefix, msg)


def _render_job_display_name(task: Task, now: Optional["datetime"] = None) -> str:
    """按模板渲染 Job 名，默认 '{task} {ymd}'。

    占位符：
      - {task}: task.name
      - {date}: YYYY-MM-DD
      - {ymd}:  YYYYMMDD
    """
    template = getattr(task, "name_template", None) or "{task} {ymd}"
    n = now or datetime.utcnow()
    return (
        template
        .replace("{task}", task.name or "")
        .replace("{date}", n.strftime("%Y-%m-%d"))
        .replace("{ymd}", n.strftime("%Y%m%d"))
        .strip()
    )


def _find_dup_link(
    session: Session,
    site_id: int,
    new_magnet: list,
    new_ed2k: list,
) -> Optional[tuple[str, int]]:
    """在同 site 已入库的 Post 中查找是否有任何 magnet/ed2k 字符串被新数据命中。

    返回 (link_type, post_id) 或 None。
    仅比对非空字符串。规模较小时直接拉取 site 内所有 Post 的链接字段做集合比对。
    """
    if not new_magnet and not new_ed2k:
        return None
    new_m_set = {m for m in (new_magnet or []) if m}
    new_e_set = {e for e in (new_ed2k or []) if e}
    if not new_m_set and not new_e_set:
        return None

    rows = session.exec(
        select(Post.id, Post.magnet, Post.ed2k).where(Post.site_id == site_id)
    ).all()
    for pid, ms, es in rows:
        for m in (ms or []):
            if m in new_m_set:
                return ("magnet", pid)
        for e in (es or []):
            if e in new_e_set:
                return ("ed2k", pid)
    return None


def _save_post(
    session: Session,
    site: Site,
    task: Task,
    job: Job,
    meta,
    detail,
) -> bool:
    """保存一条 Post（按 site_id+slug 去重；同时按 magnet/ed2k 做硬去重）。返回 True 表示新增或更新成功"""
    # 1) 硬去重：同 site 内任何已存在的 magnet/ed2k 出现即不入库
    dup = _find_dup_link(session, site.id, detail.magnet or [], detail.ed2k or [])
    if dup is not None:
        link_type, existing_id = dup
        # 跳过原因会由调用方写 Job log（"硬去重命中（链接已存在），跳过: ..."）
        return False  # 调用方负责决定是否计数/写日志

    # 2) slug 去重：原逻辑
    existing = session.exec(
        select(Post).where(Post.site_id == site.id, Post.slug == meta.slug)
    ).first()
    if existing:
        existing.title = detail.title or meta.title
        existing.author = detail.author or meta.author
        existing.cover = detail.cover or meta.cover or existing.cover
        existing.summary = meta.summary or existing.summary
        existing.post_date = detail.post_date or meta.post_date or existing.post_date
        existing.magnet = detail.magnet or existing.magnet
        existing.ed2k = detail.ed2k or existing.ed2k
        existing.task_id = task.id
        existing.job_id = job.id
        existing.raw = {"meta": meta.raw, "detail": detail.raw}
        existing.updated_at = utcnow()
        session.add(existing)
    else:
        p = Post(
            site_id=site.id,
            task_id=task.id,
            job_id=job.id,
            post_id=meta.post_id,
            slug=meta.slug,
            url=meta.url,
            title=detail.title or meta.title,
            author=detail.author or meta.author,
            cover=detail.cover or meta.cover,
            summary=meta.summary,
            post_date=detail.post_date or meta.post_date,
            magnet=detail.magnet,
            ed2k=detail.ed2k,
            raw={"meta": meta.raw, "detail": detail.raw},
        )
        session.add(p)
    session.commit()
    return True


def _emit(emit: ProgressCB, job_id: int, **payload) -> None:
    payload["job_id"] = job_id
    if emit:
        try:
            emit(payload)
        except Exception:
            pass


def _parse_kw_csv(v) -> list[str]:
    """把 list / JSON 字符串 / 换行或逗号分隔字符串 统一解析成去空小写列表"""
    import json as _json

    out: list[str] = []
    if v is None:
        return out
    if isinstance(v, list):
        items = v
    elif isinstance(v, str):
        s = v.strip()
        if not s:
            return out
        if s.startswith("["):
            try:
                parsed = _json.loads(s)
                if isinstance(parsed, list):
                    items = parsed
                else:
                    items = [s]
            except Exception:
                # 退回按分隔符切
                items = re.split(r"[\n,，;；\s]+", s)
        else:
            items = re.split(r"[\n,，;；\s]+", s)
    else:
        return out
    for x in items:
        if x is None:
            continue
        t = str(x).strip().lower()
        if t and t not in out:
            out.append(t)
    return out


def _filter_post(meta, task: Task, site: Optional[Site] = None) -> bool:
    """按 task 级关键字 / 日期过滤

    注意：站点级 include/exclude 关键词已迁移到 filter_rules + filter_keywords，
    由更高优先级的 _filter_post_with_rules 处理；这里只保留 task 级逻辑。
    返回 True 表示保留。
    """

    title_lc = (meta.title or "").lower()

    # task 级 include 关键词
    include_pools: list[str] = []
    if task.keyword:
        kw = task.keyword.strip().lower()
        if kw and kw not in include_pools:
            include_pools.append(kw)
    if include_pools and not any(kw in title_lc for kw in include_pools):
        return False

    if (task.date_from and meta.post_date and meta.post_date < task.date_from) or (
        task.date_to and meta.post_date and meta.post_date > task.date_to
    ):
        return False

    return True


# ===== 智能过滤规则 =====

# 进程内缓存：(site_id -> (loaded_at, rules_dict))
# 5 分钟内复用同一份结果，避免每条 post 都查 DB
_RULES_CACHE: dict[int, tuple[float, dict]] = {}
_RULES_CACHE_TTL = 300.0


def _load_filter_rules_for_site(site_id: int, session: Optional[Session] = None) -> dict:
    """加载站点 + 全局的有效过滤规则，按 rule_type 摊平成 3 个关键词池

    返回：
        {
            "exclude_keywords": list[str],  # 规则 exclude 池（最高优先级）
            "include_keywords": list[str],  # 规则 include 池
            "tag_keywords": list[str],      # 规则 tag 池（仅记录，不影响过滤）
            "rule_kw_pairs": list[(rule_id, kw, source)],  # 用于命中后回写 hit_count
        }
    """
    now_ts = time.time()
    cached = _RULES_CACHE.get(site_id)
    if cached and (now_ts - cached[0]) < _RULES_CACHE_TTL:
        return cached[1]

    out = {
        "exclude_keywords": [],
        "include_keywords": [],
        "tag_keywords": [],
        "rule_kw_pairs": [],
        "tag_pairs": [],
    }

    try:
        from app.models import FilterKeyword, FilterRule

        # 站点级 + 全局级 规则
        rules = session.exec(
            select(FilterRule).where(
                FilterRule.enabled == True,  # noqa: E712
                ((FilterRule.scope == "site") & (FilterRule.site_id == site_id))
                | (FilterRule.scope == "global"),
            )
        ).all() if session is not None else []

        if rules:
            rule_ids = [r.id for r in rules]
            kws = session.exec(
                select(FilterKeyword).where(FilterKeyword.rule_id.in_(rule_ids))
            ).all()
            for k in kws:
                kw = (k.keyword or "").strip().lower()
                if not kw:
                    continue
                # 找所属规则
                rule = next((r for r in rules if r.id == k.rule_id), None)
                if not rule:
                    continue
                rt = (rule.rule_type or "exclude").lower()
                if rt == "include":
                    if kw not in out["include_keywords"]:
                        out["include_keywords"].append(kw)
                elif rt == "tag":
                    if kw not in out["tag_keywords"]:
                        out["tag_keywords"].append(kw)
                    out["tag_pairs"].append((rule.id, kw))
                else:
                    if kw not in out["exclude_keywords"]:
                        out["exclude_keywords"].append(kw)
                out["rule_kw_pairs"].append((rule.id, kw, k.source or "manual"))
    except Exception as e:  # pragma: no cover
        logger.warning("加载过滤规则失败（跳过规则过滤）：%s", e)

    _RULES_CACHE[site_id] = (now_ts, out)
    return out


def invalidate_filter_rules_cache(site_id: Optional[int] = None) -> None:
    """外部（如 dislike 写入后）主动失效缓存"""
    if site_id is None:
        _RULES_CACHE.clear()
    else:
        _RULES_CACHE.pop(site_id, None)


def _filter_post_with_rules(
    meta,
    task: Task,
    site: Optional[Site] = None,
    session: Optional[Session] = None,
) -> tuple[bool, Optional[str]]:
    """带「智能过滤规则」的 post 过滤

    返回 (是否保留, 命中的 tag 规则名/None)
    优先级：
        1. 规则级 exclude（最高）
        2. 规则级 include
        3. 规则级 tag（命中只标记，不影响过滤）
        4. 站点级 + task 级（原 _filter_post）
    """
    title_lc = (meta.title or "").lower()
    rules: dict = {"exclude_keywords": [], "include_keywords": [], "tag_keywords": []}

    if site is not None:
        rules = _load_filter_rules_for_site(site.id, session=session)

    # 1) 规则级 exclude
    if rules["exclude_keywords"] and any(kw in title_lc for kw in rules["exclude_keywords"]):
        return False, None

    # 2) 规则级 include
    if rules["include_keywords"] and not any(kw in title_lc for kw in rules["include_keywords"]):
        return False, None

    # 3) tag 命中（仅标记）
    hit_tag: Optional[str] = None
    if rules.get("tag_pairs"):
        for rid, kw in rules["tag_pairs"]:
            if kw in title_lc:
                hit_tag = f"rule#{rid}"
                break

    # 4) 原站点级 + task 级过滤
    if not _filter_post(meta, task, site):
        return False, None

    return True, hit_tag


def _parse_site_list_urls(site: Site) -> list[str] | None:
    """从 site.list_urls 解析 URL 列表。支持 list / JSON 字符串 / newline 文本。"""
    raw = getattr(site, "list_urls", None)
    if not raw:
        return None
    items: list[str]
    if isinstance(raw, str):
        try:
            import json as _json
            parsed = _json.loads(raw)
            if isinstance(parsed, list):
                items = [str(x).strip() for x in parsed]
            else:
                items = [raw.strip()]
        except Exception:
            items = re.split(r"[\n,，;；\s]+", raw)
    elif isinstance(raw, list):
        items = [str(x).strip() for x in raw]
    else:
        return None

    out: list[str] = []
    for u in items:
        if u and u not in out:
            out.append(u)
    return out or None


def _iter_specs(site: Site, task: Task, job: Optional[Job] = None, session: Optional[Session] = None):
    # 站点级自定义 URL 列表：直接遍历，忽略 forum_fid
    urls = _parse_site_list_urls(site)
    if urls:
        for i, u in enumerate(urls, start=1):
            yield ListSpec(url=u, page=i)
        return

    adapter = (site.adapter or "onemei").lower()
    if adapter == "sehuatang":
        # Discuz 论坛只支持「按板块 fid 分页」一种入口；
        # 若 task.kind 不是 list_all / list_category（兼容：list_category 在 sehuatang 里也当作 list_all），
        # 给出日志告警，避免 max_pages 在用户不知情的情况下覆盖其日期/搜索意图。
        if task.kind not in ("list_all", "list_category"):
            msg = (
                f"⚠️ 站点 {site.host} (sehuatang) 不支持 task.kind={task.kind}，"
                f"Discuz 论坛只能按板块分页采集（task.category 或站点 forum_fid）。已降级为 list_all。"
            )
            if job is not None and session is not None:
                _append_log(job, msg, session)
            else:
                logger.warning(msg)
        # list_category 在 sehuatang 中：使用 task.category 作为 fid（兼容 1mei 命名）
        fid = (
            task.category
            if task.kind == "list_category" and (task.category or "").strip()
            else (getattr(site, "forum_fid", None) or None)
        )
        if not fid:
            raise ValueError(
                f"站点 {site.host} (sehuatang) 缺少板块 FID：请在「站点编辑」填 forum_fid，"
                f"或将 task.kind 设为 list_category 并填 category=fid"
            )
        yield from sehuatang.iter_forum_list_urls(
            site.base_url,
            fid=fid,
            max_pages=task.max_pages,
        )
        return

    # 默认 onemei
    yield from onemei.iter_list_urls(
        site.base_url,
        kind=task.kind,
        keyword=task.keyword,
        date_from=str(task.date_from) if task.date_from else None,
        date_to=str(task.date_to) if task.date_to else None,
        category=task.category,
        max_pages=task.max_pages,
    )


def _select_parsers(site: Site):
    """根据 site.adapter 返回 (list_parser, detail_parser)"""
    adapter = (site.adapter or "onemei").lower()
    if adapter == "sehuatang":
        return parse_discuz_list_html, parse_discuz_detail_html
    return parse_list_html, parse_detail_html


def _force_browser(site: Site) -> bool:
    """某些站点必须走浏览器（如 sehuatang 的年龄验证门）"""
    return (site.adapter or "").lower() == "sehuatang"


def _has_age_gate(page) -> bool:
    """检测当前 page 是否是年龄验证门（sehuatang 等 Discuz 站）。

    验证门特征：存在 <a class="enter-btn">满18岁，请点此进入</a>
    """
    try:
        return page.ele("css:a.enter-btn", timeout=1) is not None
    except Exception:
        return False


def _same_discuz_path(url_a: str, url_b: str) -> bool:
    """判断两个 URL 是否在同一 Discuz 板块（同 host + 同 path 前缀）。"""
    from urllib.parse import urlparse
    pa, pb = urlparse(url_a), urlparse(url_b)
    if pa.netloc != pb.netloc:
        return False
    # 列表页形如 /forum-2-1.html → 板块前缀 = /forum-2-
    seg_a = pa.path.split("/")
    seg_b = pb.path.split("/")
    # 取前 3 段作为板块前缀
    prefix_a = "/".join(seg_a[:3])
    prefix_b = "/".join(seg_b[:3])
    return prefix_a == prefix_b


# =========== 公共入口 ===========

def run_task_sync(
    task_id: int,
    *,
    progress_cb: Optional[ProgressCB] = None,
    use_browser: Optional[bool] = None,
) -> int:
    """同步执行 Task，返回 Job id

    use_browser：
      - None（默认）：自动检测。强制浏览器站点（adapter=sehuatang）走浏览器，
        其余默认走 httpx（更稳更快）。
      - True：强制使用浏览器（DrissionPage）
      - False：强制使用 httpx
    """
    from app.db import get_session

    session: Session = get_session()
    try:
        task = session.get(Task, task_id)
        if not task:
            raise RuntimeError(f"Task {task_id} 不存在")

        # 解析 site_ids（JSON 数组）。兼容旧 site_id 整数。
        import json as _json
        site_ids: list[int] = []
        raw = getattr(task, "site_ids", None)
        if isinstance(raw, list) and raw:
            site_ids = [int(x) for x in raw]
        elif isinstance(raw, str) and raw.strip():
            try:
                parsed = _json.loads(raw)
                if isinstance(parsed, list):
                    site_ids = [int(x) for x in parsed]
            except Exception:
                pass
        # 兼容旧版 site_id 单整数
        legacy_sid = getattr(task, "site_id", None)
        if not site_ids and isinstance(legacy_sid, int):
            site_ids = [legacy_sid]
        if not site_ids:
            raise RuntimeError(f"Task {task_id} 没有关联站点（site_ids 为空）")

        sites: list[Site] = []
        for sid in site_ids:
            s = session.get(Site, sid)
            if not s:
                _append_log(Job(task_id=task.id, status="running", log=[]), f"⚠️ site_id={sid} 不存在，跳过", session)
                continue
            sites.append(s)
        if not sites:
            raise RuntimeError("关联的站点都不存在")

        job = Job(
            task_id=task.id,
            status="running",
            started_at=utcnow(),
            display_name=_render_job_display_name(task),
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

        # 注册取消事件
        cancel_ev = _get_cancel_event(job_id)

        def emit(payload: dict) -> None:
            _emit(progress_cb, job_id, **payload)

        emit({"status": "running", "msg": f"开始采集：{task.name}（{len(sites)} 个站点）"})
        site_names = ", ".join(f"{s.host}({s.adapter or 'onemei'})" for s in sites)
        _append_log(
            job,
            f"启动任务 #{job_id}：name={job.display_name or task.name}, sites=[{site_names}]",
            session,
        )
        _log_progress(job_id, f"启动任务 #{job_id} name={job.display_name or task.name} sites=[{site_names}]")
        _log_progress(job_id, f"任务参数: kind={task.kind} max_pages={task.max_pages} "
                             f"keyword={task.keyword!r} date_from={task.date_from} date_to={task.date_to} "
                             f"category={task.category!r} only_with_links={task.only_with_links}")

        # 调度触发的归档任务：把 date_from/date_to 重写成"今天"
        if getattr(task, "_scheduled_run", False) and task.kind == "list_date" and not task.date_from and not task.date_to:
            today = datetime.utcnow().date()
            task.date_from = today
            task.date_to = today
            session.add(task)
            session.commit()
            _append_log(job, f"调度自动收窄日期为当日：{today.isoformat()}", session)

        overall_ok = True
        cancelled = False
        try:
            for site in sites:
                # 取消检查
                if cancel_ev.is_set():
                    _append_log(job, f"⛔ 用户取消任务", session)
                    cancelled = True
                    overall_ok = False
                    break

                # per-site use_browser 决策：强制 / 默认
                if use_browser is None:
                    if _force_browser(site):
                        ub = True
                        _append_log(job, f"站点 {site.host} 强制使用浏览器（adapter={site.adapter}）", session)
                    else:
                        # 没有强制要求的站点默认走 httpx（更稳更快）；用户可在前端勾选"使用浏览器"覆盖
                        ub = False
                else:
                    ub = bool(use_browser)

                _append_log(job, f"── 开始采集站点 {site.host} ──", session)
                _log_progress(job_id, f"── 开始采集站点 {site.host} adapter={site.adapter or 'onemei'} ──")
                try:
                    if ub:
                        _crawl_with_browser(session, site, task, job, emit, cancel_ev)
                    else:
                        _crawl_with_http(session, site, task, job, emit, cancel_ev)
                except JobCancelled:
                    cancelled = True
                    overall_ok = False
                    _append_log(job, f"⛔ 采集被取消（站点 {site.host}）", session)
                    _log_progress(job_id, f"⛔ 采集被取消（站点 {site.host}）", level=logging.WARNING)
                    break
                except Exception as e:
                    overall_ok = False
                    logger.exception("site %s failed", site.host)
                    _append_log(job, f"❌ 站点 {site.host} 采集失败：{e}", session)
                    _log_progress(job_id, f"❌ 站点 {site.host} 采集失败：{e}", level=logging.ERROR)
                    continue
                _log_progress(job_id, f"✓ 站点 {site.host} 采集完成（待计总数）")
        finally:
            _clear_cancel_event(job_id)

        if cancelled:
            job.status = "cancelled"
            job.error = "用户手动取消"
        elif overall_ok:
            job.status = "done"
        else:
            job.status = "failed"
            job.error = job.error or "部分站点失败，详见日志"
        job.finished_at = utcnow()
        session.add(job)
        session.commit()
        # 终态汇总：写一条醒目的单行到 crawler.log，便于运维 grep
        elapsed = (job.finished_at - job.started_at).total_seconds() if job.started_at else 0
        summary = (
            f"任务 #{job_id} 终态 status={job.status} 发现={job.progress_posts or 0} "
            f"入库={job.posts_saved or 0} 失败={(job.progress_posts or 0) - (job.posts_saved or 0)} "
            f"耗时={elapsed:.1f}s"
        )
        if cancelled:
            _append_log(job, f"⛔ 任务已取消：发现 {job.progress_posts}，入库 {job.posts_saved}", session)
            emit({"status": "cancelled", "msg": f"任务已取消：发现 {job.progress_posts}，入库 {job.posts_saved}"})
            _log_progress(job_id, summary, level=logging.WARNING)
        else:
            _append_log(
                job,
                f"完成：发现 {job.progress_posts}，入库 {job.posts_saved}",
                session,
            )
            emit({"status": job.status, "msg": f"采集结束：发现 {job.progress_posts}，入库 {job.posts_saved}"})
            level = logging.INFO if job.status == "done" else logging.ERROR
            _log_progress(job_id, summary, level=level)

        return job_id
    finally:
        session.close()


# =========== httpx 模式 ===========

def _crawl_with_http(
    session: Session,
    site: Site,
    task: Task,
    job: Job,
    emit: ProgressCB,
    cancel_ev: threading.Event,
) -> None:
    headers = {
        "User-Agent": site.user_agent or app_settings.default_user_agent,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if site.cookies:
        try:
            arr = json.loads(site.cookies) if isinstance(site.cookies, str) else site.cookies
            if isinstance(arr, list):
                ck = "; ".join(f"{c['name']}={c['value']}" for c in arr if "name" in c and "value" in c)
                if ck:
                    headers["Cookie"] = ck
        except Exception:
            pass

    list_parser, detail_parser = _select_parsers(site)
    specs = list(_iter_specs(site, task, job, session))
    spec_total = len(specs)
    _log_progress(job_id, f"[{site.host}] 列表页总数={spec_total} 使用浏览器={False} UA={headers['User-Agent'][:40]}…")
    for spec in specs:
        if cancel_ev.is_set():
            raise JobCancelled()
        try:
            html = fetch_html(spec.url, headers=headers)
        except Exception as e:
            _append_log(job, f"列表页请求失败 {spec.url}: {e}", session)
            _log_progress(job_id, f"[{site.host}][p{spec.page}] 列表页请求失败: {e}", level=logging.WARNING)
            continue

        items = list_parser(html, site.base_url)
        _append_log(job, f"[p{spec.page}] {spec.url} 发现 {len(items)} 篇", session)
        _log_progress(job_id, f"[{site.host}][p{spec.page}/{spec_total}] {spec.url} 发现 {len(items)} 篇")

        for meta in items:
            if cancel_ev.is_set():
                raise JobCancelled()
            keep, _ = _filter_post_with_rules(meta, task, site, session=session)
            if not keep:
                continue
            try:
                detail_html = fetch_html(meta.url, headers=headers)
            except Exception as e:
                _append_log(job, f"详情页请求失败 {meta.url}: {e}", session)
                _log_progress(job_id, f"[{site.host}][p{spec.page}] 详情页请求失败 {meta.url}: {e}", level=logging.WARNING)
                continue

            detail = detail_parser(detail_html, site.base_url)
            if task.only_with_links and not (detail.magnet or detail.ed2k):
                _log_progress(job_id, f"[{site.host}][p{spec.page}] 详情页无 magnet/ed2k，跳过: {meta.url}")
                continue

            try:
                _save_post(session, site, task, job, meta, detail)
            except Exception as e:
                _append_log(job, f"入库失败 {meta.url}: {e}", session)
                _log_progress(job_id, f"[{site.host}][p{spec.page}] 入库失败 {meta.url}: {e}", level=logging.ERROR)
                continue

            job.progress_posts = (job.progress_posts or 0) + 1
            job.posts_saved = (job.posts_saved or 0) + 1
            session.add(job)
            session.commit()
            _log_progress(
                job_id,
                f"[{site.host}][p{spec.page}] +1 saved title={(detail.title or meta.title)[:50]!r} "
                f"saved_total={job.posts_saved}",
            )
            emit(
                {
                    "status": "running",
                    "page": spec.page,
                    "found": len(items),
                    "saved": job.posts_saved,
                    "post_title": (detail.title or meta.title)[:60],
                }
            )

            time.sleep(0.2)

        job.progress_pages = (job.progress_pages or 0) + 1
        session.add(job)
        session.commit()


# =========== CloakBrowser 模式 ===========

def _crawl_with_browser(
    session: Session,
    site: Site,
    task: Task,
    job: Job,
    emit: ProgressCB,
    cancel_ev: threading.Event,
) -> None:
    user_agent = site.user_agent or app_settings.default_user_agent
    proxy = site.proxy or app_settings.proxy_url

    with make_browser(
        headless=True,
        humanize=False,
        proxy=proxy,
        user_agent=user_agent,
        fingerprint_seed=site.fingerprint_seed,
        profile_dir=app_settings.profile_dir,
    ) as page:
        nav_timeout = app_settings.default_request_timeout
        list_parser, detail_parser = _select_parsers(site)
        specs = list(_iter_specs(site, task, job, session))
        spec_total = len(specs)
        _log_progress(job_id, f"[{site.host}] 列表页总数={spec_total} 使用浏览器=True proxy={proxy or '(none)'}")
        for spec in specs:
            if cancel_ev.is_set():
                raise JobCancelled()
            try:
                page.get(spec.url, timeout=nav_timeout)
            except Exception as e:
                _append_log(job, f"列表页加载失败 {spec.url}: {e}", session)
                _log_progress(job_id, f"[{site.host}][p{spec.page}] 列表页加载失败: {e}", level=logging.WARNING)
                continue

            # ★ 年龄验证门（sehuatang 等 Discuz 站）：检测并点击 enter-btn
            # 点击后页面通常会跳到首页（href="./"），需要重新 get 真实列表页
            try:
                if _has_age_gate(page):
                    _append_log(job, f"检测到年龄验证门，点击进入：{spec.url}", session)
                    _log_progress(job_id, f"[{site.host}][p{spec.page}] 检测到年龄验证门，点击进入")
                    enter_btn = page.ele("css:a.enter-btn", timeout=5)
                    if enter_btn:
                        enter_btn.click()
                        page.wait.load_start(timeout=nav_timeout)
                        page.sleep(1.5)
                    # enter-btn 通常跳到首页，需要重抓列表页
                    if not _same_discuz_path(page.url, spec.url):
                        page.get(spec.url, timeout=nav_timeout)
                        page.sleep(1.5)
            except Exception as e:
                _append_log(job, f"年龄验证门处理失败（继续尝试解析）：{e}", session)
                _log_progress(job_id, f"[{site.host}][p{spec.page}] 年龄验证门处理失败: {e}", level=logging.WARNING)

            html = page.html
            items = list_parser(html, site.base_url)
            _append_log(job, f"[p{spec.page}] {spec.url} 发现 {len(items)} 篇", session)
            _log_progress(job_id, f"[{site.host}][p{spec.page}/{spec_total}] {spec.url} 发现 {len(items)} 篇")

            for meta in items:
                if cancel_ev.is_set():
                    raise JobCancelled()
                keep, _ = _filter_post_with_rules(meta, task, site, session=session)
                if not keep:
                    continue
                try:
                    page.get(meta.url, timeout=nav_timeout)
                except Exception as e:
                    _append_log(job, f"详情页加载失败 {meta.url}: {e}", session)
                    _log_progress(job_id, f"[{site.host}][p{spec.page}] 详情页加载失败 {meta.url}: {e}", level=logging.WARNING)
                    continue

                detail = detail_parser(page.html, site.base_url)
                if task.only_with_links and not (detail.magnet or detail.ed2k):
                    _append_log(
                        job,
                        f"详情页无 magnet/ed2k，跳过: {meta.url}",
                        session,
                    )
                    _log_progress(job_id, f"[{site.host}][p{spec.page}] 详情页无 magnet/ed2k，跳过: {meta.url}")
                    continue

                try:
                    saved = _save_post(session, site, task, job, meta, detail)
                except Exception as e:
                    _append_log(job, f"入库失败 {meta.url}: {e}", session)
                    _log_progress(job_id, f"[{site.host}][p{spec.page}] 入库失败 {meta.url}: {e}", level=logging.ERROR)
                    continue

                if not saved:
                    # 硬去重命中：不计 saved，写日志以便用户知晓
                    _append_log(
                        job,
                        f"硬去重命中（链接已存在），跳过: {meta.url}",
                        session,
                    )
                    _log_progress(job_id, f"[{site.host}][p{spec.page}] 硬去重命中（链接已存在），跳过: {meta.url}")
                    continue

                job.progress_posts = (job.progress_posts or 0) + 1
                job.posts_saved = (job.posts_saved or 0) + 1
                session.add(job)
                session.commit()
                _log_progress(
                    job_id,
                    f"[{site.host}][p{spec.page}] +1 saved title={(detail.title or meta.title)[:50]!r} "
                    f"saved_total={job.posts_saved}",
                )
                emit(
                    {
                        "status": "running",
                        "page": spec.page,
                        "found": len(items),
                        "saved": job.posts_saved,
                        "post_title": (detail.title or meta.title)[:60],
                    }
                )

            job.progress_pages = (job.progress_pages or 0) + 1
            session.add(job)
            session.commit()
            time.sleep(0.5)


# =========== 线程包装 ===========

def run_task_in_thread(task_id: int) -> int:
    """在线程中跑采集（避免阻塞事件循环），返回 task_id"""
    def runner():
        try:
            run_task_sync(task_id)
        except Exception as e:
            logger.exception("runner failed: %s", e)

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    return task_id
