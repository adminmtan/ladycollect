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
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterator, Optional

import httpx
from sqlmodel import Session, select

from app.config import settings as app_settings
from app.crawler import onemei, sehuatang  # sehuatang adapter 占位：保留模块以兼容旧站点，待重新开发
from app.crawler.browser import make_page
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
    """外部请求取消一个 Job。

    返回 True 表示信号已发出（可能 job 还没启动采集循环，但下次进入 cancel_ev 检查时
    会立刻命中并 raise JobCancelled）。

    设计原因：模块级 _cancel_events 在 uvicorn 进程重启后会清空；如果用户重启过 backend
    而旧 Job 仍在 DB 显示 running，旧 event 已丢失。必须让 request_cancel_job 仍然能
    set 一个新 event，让后续 runner 进入时立刻 cancel。
    """
    with _cancel_lock:
        ev = _cancel_events.get(job_id)
        if ev is None:
            # event 缺失（采集循环还没跑到 _get_cancel_event 或进程重启丢失）—— 创建一个
            ev = threading.Event()
            _cancel_events[job_id] = ev
        ev.set()
        return True


class JobCancelled(Exception):
    """用户主动取消时抛出"""


# ============ 采集规格（spec）级重试器 ============
# 设计目标：单页加载偶发失败（timeout / connection reset / browser pool 瞬时占满）
# 不应直接 continue 跳页漏数据；应分级重试后再决定。
#
# 关键约定：
# - 调用方传入一个零参 callable（通常是 page.get + 后续解析的闭包），返回任何值即视为成功
# - 仅 retryable_exceptions 白名单内的异常重试；其它异常（如 4xx HTTPError / 解析失败）
#   立即抛，由外层 except 接住后 continue 跳页
# - 任何 attempt 之前检查 cancel_ev.is_set()；触发则抛 JobCancelled 让调度器中断 Job
# - total_timeout_s 整体上限 + sleeps 退避序列；到上限抛最后一次异常（外层可 continue）
# - 不引入 tenacity 等新依赖；自管 30 行


class NonRetryableError(Exception):
    """caller 把某种异常升格为「永久失败，不重试」（如 HTTP 4xx）"""


# 白名单：网络瞬时错误 + Playwright/DrissionPage 常见瞬时错误
# 注意：尽量窄，避免 catch-all 重试掩盖真 bug
SPEC_RETRYABLE_EXCEPTIONS: tuple = (
    TimeoutError,        # Python 内置；socket timeout / asyncio timeout
    ConnectionError,     # DNS / refused / reset
    OSError,             # 低层 socket 错误（macOS 上 ETIMEDOUT 也走 OSError）
)


@dataclass
class _RetryResult:
    """spec_with_retry 上下文返回值。caller 通过 .run(callable) 调用被重试的函数"""

    _ctx: "_RetryCtx"

    def run(self, fn) -> object:
        """跑一次带重试的调用。返回 fn 的返回值；最后一次异常会重抛出。"""
        return self._ctx._execute_with_retry(fn)


@dataclass
class _RetryCtx:
    spec_name: str
    cancel_ev: threading.Event
    retryable_exceptions: tuple
    sleeps: tuple
    total_timeout_s: float
    on_retry: Optional[callable] = None  # (attempt, exc, wait_s) -> None; 用于记日志

    def _check_cancel(self) -> None:
        if self.cancel_ev is not None and self.cancel_ev.is_set():
            raise JobCancelled(f"cancel received during {self.spec_name}")

    def _execute_with_retry(self, fn) -> object:
        start = time.monotonic()
        last_exc: Optional[BaseException] = None
        max_attempts = max(len(self.sleeps), 1)
        for attempt in range(1, max_attempts + 1):
            self._check_cancel()
            # total_timeout 守门：留出 0.5s 给下一次 attempt + sleep
            if time.monotonic() - start > self.total_timeout_s:
                if last_exc is not None:
                    raise last_exc
                raise TimeoutError(
                    f"{self.spec_name} total_timeout={self.total_timeout_s}s exceeded "
                    f"before attempt {attempt}"
                )
            try:
                return fn()
            except JobCancelled:
                raise  # 始终向上传递
            except self.retryable_exceptions as e:
                last_exc = e
                if attempt >= max_attempts:
                    raise  # 用尽
                wait_s = self.sleeps[attempt - 1] if attempt - 1 < len(self.sleeps) else 0
                if self.on_retry:
                    try:
                        self.on_retry(attempt, e, wait_s)
                    except Exception:  # pragma: no cover
                        pass
                if wait_s > 0:
                    time.sleep(wait_s)
                continue
            except NonRetryableError:
                raise  # 永久失败，立刻抛
        # 不应到达这里
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"{self.spec_name} retry loop exited unexpectedly")


@contextmanager
def spec_with_retry(
    spec_name: str,
    cancel_ev: threading.Event,
    *,
    retryable_exceptions: tuple = SPEC_RETRYABLE_EXCEPTIONS,
    sleeps: tuple = (5, 15),
    total_timeout_s: float = 60.0,
    on_retry: Optional[callable] = None,
) -> Iterator[_RetryResult]:
    """采集单页 spec 重试上下文。

    用法：
        with spec_with_retry(
            spec_name=f"[{site.host}][p{spec.page}] 列表页",
            cancel_ev=cancel_ev,
            on_retry=lambda a, e, w: _log_progress(job_id, f"retry {a}/2: {e}"),
        ) as r:
            r.run(lambda: _do_load(spec.url))

    语义：
    - 重试次数 = max(len(sleeps), 1)（即 sleeps=(5,15) → 3 次 attempt，第 1 次立刻、
      第 2 次 sleep 5s、第 3 次 sleep 15s）
    - 仅 retryable_exceptions 白名单内的异常触发重试
    - cancel_ev 触发或 total_timeout_s 触发 → 抛（JobCancelled / 最后一次异常）
    """
    ctx = _RetryCtx(
        spec_name=spec_name,
        cancel_ev=cancel_ev,
        retryable_exceptions=retryable_exceptions,
        sleeps=sleeps,
        total_timeout_s=total_timeout_s,
        on_retry=on_retry,
    )
    yield _RetryResult(_ctx=ctx)


# 共享 httpx 客户端（线程级单例，连接复用）
_http_client: Optional[httpx.Client] = None


def _http() -> httpx.Client:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(
            timeout=app_settings.default_request_timeout,
            follow_redirects=True,
            headers={"User-Agent": app_settings.default_user_agent},
            # macOS 系统代理 (PAC) 会自动注入 127.0.0.1:7890 之类的代理地址；
            # 但 7890 通常没进程监听，httpx 走代理会 Connection refused。
            # 显式 trust_env=False 直连，避免 macOS 用户中招。
            trust_env=False,
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


def _in_date_range(
    post_date,
    date_from,
    date_to,
) -> bool:
    """list_date 兜底过滤：post_date 为空时不过滤（保留向后兼容）。

    只要列表解析出的 post_date 在 [date_from, date_to] 闭区间内就保留。
    解析不出日期的帖子不剔除，避免列表不带日期的站点被误杀。
    """
    if post_date is None:
        return True
    if date_from and post_date < date_from:
        return False
    if date_to and post_date > date_to:
        return False
    return True


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
        # Discuz 论坛按板块 fid 分页抓取
        # list_date 模式：list_date 与 max_pages 无关 —— 翻页直到 date_from 之前为止。
        # runner 里检测 "这一页 post_date 全部 < date_from" 时停止。
        # 这里仍生成 max_pages 个 URL 作为安全上限（默认 100 页 ≈ 3000 帖 ≈ 几个月归档），
        # runner 提前 break 可避免无谓请求。
        if task.kind not in ("list_all", "list_date"):
            msg = (
                f"⚠️ 站点 {site.host} (sehuatang) 不支持 task.kind={task.kind}，"
                f"已降级为 list_all（按板块 fid 分页）。"
            )
            if job is not None and session is not None:
                _append_log(job, msg, session)
            else:
                logger.warning(msg)
        elif task.kind == "list_date":
            info = (
                f"ℹ️ 站点 {site.host} (sehuatang) list_date 模式：按板块 fid 自动翻页，"
                f"直到 date_from={task.date_from} 之前停止；max_pages 仅作为安全上限（默认 100）。"
            )
            if job is not None and session is not None:
                _append_log(job, info, session)
            else:
                logger.info(info)
        fid = (
            task.category
            if task.category and (task.category or "").strip()
            else (getattr(site, "forum_fid", None) or None)
        )
        if not fid:
            raise ValueError(
                f"站点 {site.host} (sehuatang) 缺少板块 FID：请在「站点编辑」填 forum_fid，"
                f"或将 task.category 填为板块 fid"
            )
        # list_date 模式下 max_pages 强制最小 100 页（≈ 几个月归档），保证能翻到 date_from
        effective_max = max(task.max_pages, 100)
        if effective_max != task.max_pages:
            logger.info(
                "sehuatang list_date: max_pages=%d 提到 %d 以保证能翻到 date_from=%s",
                task.max_pages, effective_max, task.date_from,
            )
        yield from sehuatang.iter_forum_list_urls(
            site.base_url,
            fid=fid,
            max_pages=effective_max,
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
        # 色花堂解析器仍然可用（httpx 拿到 HTML 后可走 parse_discuz_*），
        # 但浏览器路径已移除，跳过发生在 _build_iter_list_urls。
        return parse_discuz_list_html, parse_discuz_detail_html
    return parse_list_html, parse_detail_html


# ----- 浏览器路径辅助函数 -----
def _force_browser(site: Site) -> bool:
    """某些站点 httpx 拿不到内容（如 sehuatang 的 CF challenge），必须走浏览器。"""
    adapter = (site.adapter or "").lower()
    if adapter == "sehuatang":
        return True
    # 兜底：站点级显式标记 use_browser 也可触发
    return bool(getattr(site, "use_browser", False))


def _has_age_gate(page) -> bool:
    """检测当前 page 是否是年龄验证门（sehuatang 等 Discuz 站）。

    验证门特征：存在 <a class="enter-btn">满18岁，请点此进入</a>
    Playwright 用 locator() 替代 DrissionPage 的 raw.eles()。
    """
    try:
        return page.raw.locator("a.enter-btn").count() > 0
    except Exception:
        return False


# Cloudflare challenge 页特征（runtime evidence：sehuatang.org 在 headless 浏览器首次访问时返回的页面）
_CF_MARKERS = (
    "Just a moment",
    "cf-challenge-running",
    "cf_chl_opt",
    "Checking your browser",
)


def _detect_cf_challenge(html: str) -> bool:
    """检测当前 HTML 是否是 Cloudflare challenge 页（不是真实列表页）。

    CF challenge 页特征：title="Just a moment..."、含 cf-challenge-running、
    或带 cf_chl_opt JS 标志。出现这些特征意味着 user_data 里没有有效的
    cf_clearance cookie（IP 已变 / profile 是空的 / 浏览器被检测为 headless）。
    """
    if not html:
        return False
    head = html[:8192]  # CF challenge HTML 通常很短（< 50KB），只看头部
    return any(m in head for m in _CF_MARKERS)


def _reload_list_page(page, url: str, nav_timeout_s: int) -> None:
    """spec 级重试器用：单次 page.get + age gate 重新加载。

    DrissionPage 的 page.get() 自带内部 retry=3 (CF challenge 重试)，
    这里只负责外部那一层；age gate 处理也复跑一次，确保列表特征出现。
    """
    page.get(url, timeout=nav_timeout_s)
    if _has_age_gate(page):
        btn = page.raw.locator("a.enter-btn").first
        if btn.count() > 0:
            btn.click()
            time.sleep(2)
            page.get(url, timeout=nav_timeout_s)


def _cf_warmup_retry(page, job, session, job_id: int, site_host: str, page_num: int, url: str) -> bool:
    """CF challenge 时尝试等更久 + 重新 GET。

    首次 GET CF challenge 通常 5-30s 才完成 JS proof-of-work。
    DrissionPage 的 page.get() 默认只等 DOMContentLoaded，不等 CF JS 完成，
    所以加 retry+更长 timeout 触发 DrissionPage 内部重试逻辑。

    返回 True 表示已成功通过 CF（页面含列表特征），False 表示仍被拦截。
    """
    for attempt, wait_s in enumerate((15, 30, 45), start=1):
        _log_progress(
            job_id,
            f"[{site_host}][p{page_num}] CF challenge 第 {attempt} 次重试（wait={wait_s}s）: {url}",
        )
        try:
            page.get(url, timeout=wait_s + 10, retry=1)
            time.sleep(wait_s)
            html = page.html
            if not _detect_cf_challenge(html):
                _append_log(
                    job, f"[p{page_num}] CF challenge 第 {attempt} 次重试成功（waited {wait_s}s）", session,
                )
                return True
        except Exception as e:
            _log_progress(
                job_id,
                f"[{site_host}][p{page_num}] CF 重试异常: {e}",
                level=logging.WARNING,
            )
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

                # per-site 抓取方式决策：adapter 强制浏览器 → 浏览器；其余默认 httpx
                ub = bool(use_browser) if use_browser is not None else _force_browser(site)
                if ub:
                    _append_log(
                        job,
                        f"站点 {site.host} 使用浏览器（adapter={site.adapter or 'onemei'}）",
                        session,
                    )

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
                except NotImplementedError as e:
                    # adapter 暂不支持——不算采集失败，按"跳过该站点"处理
                    _append_log(job, f"⏭ 站点 {site.host} 已跳过：{e}", session)
                    _log_progress(job_id, f"⏭ 站点 {site.host} 已跳过：{e}", level=logging.WARNING)
                    continue
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
    # sehuatang 等"暂不支持"的 adapter 在 _iter_specs 抛 NotImplementedError，
    # 主循环会捕获并跳过；这里只是提示性日志，实际不会被执行到。
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

    job_id = job.id
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
        # list_date 模式：按列表内日期二次过滤（仅对 Discuz/列表带日期的 adapter 生效）
        # onemei 等已经走 URL 日期过滤，这里是兜底
        if task.kind == "list_date" and (task.date_from or task.date_to):
            before = len(items)
            items = [m for m in items if _in_date_range(m.post_date, task.date_from, task.date_to)]
            if before != len(items):
                _append_log(
                    job,
                    f"[p{spec.page}] 日期过滤 {before}→{len(items)} 篇 "
                    f"(date_from={task.date_from}, date_to={task.date_to})",
                    session,
                )
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


# =========== 浏览器采集（DrissionPage） ===========
def _crawl_with_browser(
    session: Session,
    site: Site,
    task: Task,
    job: Job,
    emit: ProgressCB,
    cancel_ev: threading.Event,
) -> None:
    """基于 DrissionPage 的浏览器采集（替代 CloakBrowser/Playwright）。

    为何切换：Playwright headless 被 CF 检测（runtime evidence: 60s×6 次仍 timeout）。
    DrissionPage 内置 Chromium 内核 + 真实 user_data_dir，CF bypass 更接近真实浏览器。

    DrissionPage 的 page.get() 自带：
    - 等 domcontentloaded / load 事件完成
    - 失败自动 retry（默认 3 次，处理 CF challenge 重试）
    - 返回成功 = 页面已加载（含 challenge JS 执行完成）

    因此不再需要显式 wait_for_selector / wait_for_function。
    """
    user_agent = site.user_agent or app_settings.default_user_agent
    proxy = site.proxy or app_settings.proxy_url
    job_id = job.id
    nav_timeout_s = max(app_settings.default_request_timeout, 30)

    with make_page(
        headless=True,
        proxy=proxy,
        user_agent=user_agent,
        profile_dir=app_settings.profile_dir,
    ) as page:
        list_parser, detail_parser = _select_parsers(site)
        specs = list(_iter_specs(site, task, job, session))
        spec_total = len(specs)
        _log_progress(
            job_id,
            f"[{site.host}] 列表页总数={spec_total} 使用浏览器=CloakBrowser proxy={proxy or '(none)'}",
        )

        for spec in specs:
            if cancel_ev.is_set():
                raise JobCancelled()
            try:
                page.get(spec.url, timeout=nav_timeout_s)
                # 先处理 age gate（点击 enter-btn 会跳到真实列表），再等列表特征元素
                # CF challenge 通常 5-30s 完成
                try:
                    if _has_age_gate(page):
                        _append_log(
                            job, f"检测到年龄验证门，点击进入：{spec.url}", session,
                        )
                        _log_progress(
                            job_id,
                            f"[{site.host}][p{spec.page}] 检测到年龄验证门，点击进入",
                        )
                        btn = page.raw.locator("a.enter-btn").first
                        if btn.count() > 0:
                            btn.click()
                            time.sleep(2)
                        if not _same_discuz_path(page.url, spec.url):
                            page.get(spec.url, timeout=nav_timeout_s)
                except Exception as gate_err:
                    _log_progress(
                        job_id,
                        f"[{site.host}][p{spec.page}] age gate 处理失败: {gate_err}",
                        level=logging.WARNING,
                    )
                ok = page.wait_loaded('a[href*="thread-"]', timeout=nav_timeout_s)
                if not ok:
                    # 诊断：区分"CF challenge 还在跑" vs "真的反爬"
                    cur_html = page.html or ""
                    cur_title = page.title()
                    is_cf = _detect_cf_challenge(cur_html)
                    _log_progress(
                        job_id,
                        f"[{site.host}][p{spec.page}] wait_loaded 超时 → "
                        f"is_cf_challenge={is_cf} title={cur_title!r} html_len={len(cur_html)}",
                    )
                    if is_cf:
                        # CF challenge 还没完成（IP 没绑 cf_clearance / profile 空的）
                        # 尝试等更久 + 重试，让 DrissionPage 内部给 CF JS challenge 充分时间
                        if _cf_warmup_retry(page, job, session, job_id, site.host, spec.page, spec.url):
                            ok = page.wait_loaded('a[href*="thread-"]', timeout=20)
                    if not ok:
                        _append_log(
                            job,
                            f"列表页等不到 thread- 链接（CF 拦截）: {spec.url}",
                            session,
                        )
                        _log_progress(
                            job_id,
                            f"[{site.host}][p{spec.page}] 等不到 thread- 链接（CF 拦截）",
                            level=logging.WARNING,
                        )
                        continue
            except SPEC_RETRYABLE_EXCEPTIONS as e:
                # 瞬时错误（timeout / connection reset / DNS 抖动）→ 分级重试 1 次
                # 不要无限重试，规格级 total_timeout 60s 兜底；最终失败再 continue 跳页
                _log_progress(
                    job_id,
                    f"[{site.host}][p{spec.page}] 列表页加载瞬时失败: {e}，尝试 spec 级重试",
                    level=logging.WARNING,
                )
                retry_ok = False
                try:
                    with spec_with_retry(
                        spec_name=f"[{site.host}][p{spec.page}] 列表页",
                        cancel_ev=cancel_ev,
                        sleeps=(5, 15),
                        total_timeout_s=60,
                        on_retry=lambda a, exc, w: _log_progress(
                            job_id,
                            f"[{site.host}][p{spec.page}] 列表页第 {a} 次重试 (wait={w}s): {exc}",
                            level=logging.WARNING,
                        ),
                    ) as r:
                        r.run(lambda: _reload_list_page(page, spec.url, nav_timeout_s))
                        ok2 = page.wait_loaded('a[href*="thread-"]', timeout=nav_timeout_s)
                        if ok2:
                            retry_ok = True
                except JobCancelled:
                    raise
                except SPEC_RETRYABLE_EXCEPTIONS as e2:
                    _append_log(job, f"列表页重试用尽 {spec.url}: {e2}", session)
                    _log_progress(
                        job_id,
                        f"[{site.host}][p{spec.page}] 列表页重试用尽: {e2}",
                        level=logging.WARNING,
                    )
                except Exception as e2:
                    _append_log(job, f"列表页重试异常 {spec.url}: {e2}", session)
                    _log_progress(
                        job_id,
                        f"[{site.host}][p{spec.page}] 列表页重试异常: {e2}",
                        level=logging.WARNING,
                    )
                if not retry_ok:
                    continue
            except Exception as e:
                _append_log(job, f"列表页加载失败 {spec.url}: {e}", session)
                _log_progress(
                    job_id,
                    f"[{site.host}][p{spec.page}] 列表页加载失败: {e}",
                    level=logging.WARNING,
                )
                continue

            html = page.html
            raw_items = list_parser(html, site.base_url)
            # list_date 早停判定：用 raw_items（过滤前）—— 整页 post_date 都早于 date_from 才停，
            # 否则过滤后是 0 仍然不知道是"日期不对"还是"抓 0 篇"
            if task.kind == "list_date" and task.date_from and raw_items:
                all_dates = [m.post_date for m in raw_items if m.post_date is not None]
                if all_dates and max(all_dates) < task.date_from:
                    _log_progress(
                        job_id,
                        f"[{site.host}][p{spec.page}] 这一页所有 post_date 全部 < date_from={task.date_from}（最老={max(all_dates)}），"
                        f"已翻到归档起点之前，停止翻页（剩余 {spec_total - spec.page} 页不再抓）",
                    )
                    _append_log(
                        job,
                        f"[p{spec.page}] 这一页 post_date 全部早于 date_from，停止翻页",
                        session,
                    )
                    break
            # list_date 兜底：按列表内日期二次过滤
            if task.kind == "list_date" and (task.date_from or task.date_to):
                before = len(raw_items)
                items_meta = [
                    m for m in raw_items
                    if _in_date_range(m.post_date, task.date_from, task.date_to)
                ]
                if before != len(items_meta):
                    _append_log(
                        job,
                        f"[p{spec.page}] 日期过滤 {before}→{len(items_meta)} 篇 "
                        f"(date_from={task.date_from}, date_to={task.date_to})",
                        session,
                    )
            else:
                items_meta = raw_items
            _append_log(job, f"[p{spec.page}] {spec.url} 发现 {len(items_meta)} 篇", session)
            _log_progress(
                job_id,
                f"[{site.host}][p{spec.page}/{spec_total}] {spec.url} 发现 {len(items_meta)} 篇",
            )

            for meta in items_meta:
                if cancel_ev.is_set():
                    raise JobCancelled()
                keep, _ = _filter_post_with_rules(meta, task, site, session=session)
                if not keep:
                    continue
                try:
                    page.get(meta.url, timeout=nav_timeout_s)
                    if _has_age_gate(page):
                        btn = page.raw.locator("a.enter-btn").first
                        if btn.count() > 0:
                            btn.click()
                            time.sleep(2)
                        page.get(meta.url, timeout=nav_timeout_s)
                    detail_html = page.html
                    # 诊断：详情页 HTML 长度 + 是否含 magnet 字样（不发 HTML 全文，只发计数）
                    _log_progress(
                        job_id,
                        f"[{site.host}][p{spec.page}] 详情页 html_len={len(detail_html)} "
                        f"含 magnet={'magnet:?' in detail_html} "
                        f"含 blockcode={'blockcode' in detail_html}",
                    )
                except Exception as e:
                    _append_log(job, f"详情页加载失败 {meta.url}: {e}", session)
                    _log_progress(
                        job_id,
                        f"[{site.host}][p{spec.page}] 详情页加载失败 {meta.url}: {e}",
                        level=logging.WARNING,
                    )
                    continue

                detail = detail_parser(detail_html, site.base_url)
                if task.only_with_links and not (detail.magnet or detail.ed2k):
                    _append_log(job, f"详情页无 magnet/ed2k，跳过: {meta.url}", session)
                    _log_progress(
                        job_id,
                        f"[{site.host}][p{spec.page}] 详情页无 magnet/ed2k，跳过: {meta.url}",
                    )
                    continue

                try:
                    saved = _save_post(session, site, task, job, meta, detail)
                except Exception as e:
                    _append_log(job, f"入库失败 {meta.url}: {e}", session)
                    _log_progress(
                        job_id,
                        f"[{site.host}][p{spec.page}] 入库失败 {meta.url}: {e}",
                        level=logging.ERROR,
                    )
                    continue

                prev_saved = job.posts_saved or 0
                if not saved:
                    _append_log(job, f"硬去重命中（链接已存在），跳过: {meta.url}", session)
                    _log_progress(
                        job_id,
                        f"[{site.host}][p{spec.page}] 硬去重命中（链接已存在），跳过: {meta.url}",
                    )
                    continue

                job.progress_posts = (job.progress_posts or 0) + 1
                job.posts_saved = (job.posts_saved or 0) + 1
                session.add(job)
                session.commit()
                # 详情页成功入库：写一行到 job.log，前端能立刻看到「不是卡了，是在存详情页」
                _append_log(
                    job,
                    f"[p{spec.page}] +{job.posts_saved - prev_saved} 已存 #{(detail.title or meta.title)[:40]!r}",
                    session,
                )
                _log_progress(
                    job_id,
                    f"[{site.host}][p{spec.page}] +1 saved title={(detail.title or meta.title)[:50]!r} "
                    f"saved_total={job.posts_saved}",
                )
                emit(
                    {
                        "status": "running",
                        "page": spec.page,
                        "found": len(items_meta),
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
