"""APScheduler 后台调度

- 启动时扫描所有 schedule_enabled=1 且 cron 非空的 Task，加到调度器
- Task 的 cron/schedule_enabled 变更时，调用 apply_task() 同步
- 删除 Task 时调用 remove_task()
- 每次触发时在线程里跑 run_task_sync，并打上 _scheduled_run 标记
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from app.db import engine
from app.models import Task, utcnow

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None
_lock = threading.Lock()


def get_scheduler() -> BackgroundScheduler:
    """懒加载全局调度器（首次调用启动）"""
    global _scheduler
    if _scheduler is None:
        with _lock:
            if _scheduler is None:
                _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
                _scheduler.start()
                logger.info("APScheduler 启动完成（时区 Asia/Shanghai）")
    return _scheduler


def _job_id(task_id: int) -> str:
    return f"task-{task_id}"


def apply_task(task: Task) -> None:
    """根据 task.cron + schedule_enabled 增/改/删调度项"""
    sched = get_scheduler()
    jid = _job_id(task.id)
    try:
        sched.remove_job(jid)
    except Exception:
        pass

    if not task.schedule_enabled or not (task.cron or "").strip():
        # 关掉调度，清空 next_run_at
        task.next_run_at = None
        return

    try:
        trigger = CronTrigger.from_crontab(task.cron.strip(), timezone="Asia/Shanghai")
    except Exception as e:
        logger.warning("Task %s cron 解析失败：%s (%r)", task.id, e, task.cron)
        task.next_run_at = None
        return

    sched.add_job(
        _run_scheduled,
        trigger=trigger,
        id=jid,
        args=[task.id],
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    nxt = sched.get_job(jid).next_run_time if sched.get_job(jid) else None
    task.next_run_at = nxt
    logger.info("Task %s 已调度：cron=%r, next=%s", task.id, task.cron, nxt)


def remove_task(task_id: int) -> None:
    sched = get_scheduler()
    try:
        sched.remove_job(_job_id(task_id))
    except Exception:
        pass


def _run_scheduled(task_id: int) -> None:
    """调度触发的入口：在线程里跑采集，并在 task 上挂 _scheduled_run 标记"""
    from app.crawler.runner import run_task_sync  # 局部 import 避免循环

    logger.info("调度触发 Task %s", task_id)

    def _thread():
        try:
            with Session(engine) as s:
                t = s.get(Task, task_id)
                if not t:
                    logger.warning("Task %s 不存在，跳过调度执行", task_id)
                    return
                # 标记：让 run_task_sync 知道是调度触发（用于自动收窄 date）
                t._scheduled_run = True  # type: ignore[attr-defined]
                # 记录 last_run_at
                t.last_run_at = utcnow()
                s.add(t)
                s.commit()
            run_task_sync(task_id)
        except Exception as e:
            logger.exception("调度执行 Task %s 失败：%s", task_id, e)
        finally:
            # 重新计算 next_run_at
            try:
                sched = get_scheduler()
                job = sched.get_job(_job_id(task_id))
                with Session(engine) as s:
                    t = s.get(Task, task_id)
                    if t and job is not None:
                        t.next_run_at = job.next_run_time
                        s.add(t)
                        s.commit()
            except Exception:
                pass

    threading.Thread(target=_thread, daemon=True).start()


def bootstrap() -> None:
    """启动时加载所有启用的 Task 到调度器"""
    try:
        sched = get_scheduler()
    except Exception as e:
        logger.warning("调度器初始化失败：%s", e)
        return

    try:
        with Session(engine) as s:
            tasks = s.exec(select(Task).where(Task.schedule_enabled == True)).all()  # noqa: E712
            for t in tasks:
                try:
                    apply_task(t)
                except Exception as e:
                    logger.warning("Task %s 加入调度失败：%s", t.id, e)
        logger.info("调度启动：已加载 %d 个定时任务", len(sched.get_jobs()))
    except Exception as e:
        logger.warning("bootstrap 失败：%s", e)
