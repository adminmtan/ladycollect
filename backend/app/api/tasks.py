"""采集任务 API"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from app.crawler.runner import run_task_sync
from app.db import get_session
from app.models import Job, Site, Task, utcnow
from app.schemas import JobRead, TaskCreate, TaskRead, TaskUpdate
from app.scheduler import apply_task, get_scheduler, remove_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _resolve_site_ids(task: Task) -> list[int]:
    """从 Task.site_ids（JSON 数组或字符串）解析出 int 列表"""
    raw = task.site_ids
    if not raw:
        return []
    if isinstance(raw, list):
        try:
            return [int(x) for x in raw]
        except Exception:
            return []
    if isinstance(raw, str):
        try:
            import json as _json
            parsed = _json.loads(raw)
            if isinstance(parsed, list):
                return [int(x) for x in parsed]
        except Exception:
            pass
    return []


@router.get("", response_model=list[TaskRead])
def list_tasks(site_id: Optional[int] = None, session: Session = Depends(get_session)):
    q = select(Task)
    rows = session.exec(q.order_by(Task.id.desc())).all()
    if site_id is not None:
        rows = [t for t in rows if site_id in _resolve_site_ids(t)]
    # 同步 next_run_at（内存里的调度器最准）+ 当前 running Job
    try:
        sched = get_scheduler()
    except Exception:
        sched = None
    # 一次查所有 running jobs，构建 task_id -> job_id 映射
    running_jobs = session.exec(select(Job.id, Job.task_id).where(Job.status == "running")).all()
    running_by_task: dict[int, int] = {j_task_id: j_id for j_id, j_task_id in running_jobs}
    # 转为响应模型，避免直接 setattr 到 SQLModel ORM 上（不允许动态字段）
    out: list[TaskRead] = []
    for t in rows:
        t_read = TaskRead.model_validate(t)
        t_read.running_job_id = running_by_task.get(t.id)
        if sched is not None and t.schedule_enabled:
            job = sched.get_job(f"task-{t.id}")
            t_read.next_run_at = job.next_run_time if job else None
        out.append(t_read)
    return out


@router.post("", response_model=TaskRead)
def create_task(payload: TaskCreate, session: Session = Depends(get_session)):
    site_ids = payload.site_ids
    if not site_ids:
        raise HTTPException(400, "site_ids 不能为空")
    for sid in site_ids:
        site = session.get(Site, sid)
        if not site:
            raise HTTPException(404, f"site {sid} 不存在")
    task = Task(**payload.model_dump())
    session.add(task)
    session.commit()
    session.refresh(task)
    # 同步到调度器
    try:
        apply_task(task)
        session.add(task)
        session.commit()
        session.refresh(task)
    except Exception as e:
        logger.warning("创建调度失败：%s", e)
    out = TaskRead.model_validate(task)
    out.running_job_id = None
    return out


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "task 不存在")
    try:
        sched = get_scheduler()
        if task.schedule_enabled:
            job = sched.get_job(f"task-{task_id}")
            task.next_run_at = job.next_run_time if job else None
    except Exception:
        pass
    out = TaskRead.model_validate(task)
    # 找 running job
    rj = session.exec(
        select(Job.id).where(Job.task_id == task_id, Job.status == "running")
    ).first()
    out.running_job_id = int(rj) if rj is not None else None
    return out


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(task_id: int, payload: TaskUpdate, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "task 不存在")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(task, k, v)
    session.add(task)
    session.commit()
    session.refresh(task)
    # 调度同步
    try:
        apply_task(task)
        session.add(task)
        session.commit()
        session.refresh(task)
    except Exception as e:
        logger.warning("更新调度失败：%s", e)
    out = TaskRead.model_validate(task)
    rj = session.exec(
        select(Job.id).where(Job.task_id == task_id, Job.status == "running")
    ).first()
    out.running_job_id = int(rj) if rj is not None else None
    return out


@router.delete("/{task_id}")
def delete_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "task 不存在")
    try:
        remove_task(task_id)
    except Exception as e:
        logger.warning("移除调度失败：%s", e)
    session.delete(task)
    session.commit()
    return {"ok": True}


@router.post("/{task_id}/run")
def run_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    use_browser: Optional[bool] = None,
    session: Session = Depends(get_session),
):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "task 不存在")
    if not _resolve_site_ids(task):
        raise HTTPException(400, "task 没有关联站点，请在编辑任务里勾选站点")

    def _bg():
        try:
            run_task_sync(task_id, use_browser=use_browser)
        except Exception as e:
            logger.exception("background run failed: %s", e)

    threading.Thread(target=_bg, daemon=True).start()

    return {"ok": True, "task_id": task_id, "use_browser": use_browser, "msg": "已在后台启动"}


@router.post("/{task_id}/stop")
def stop_task(task_id: int, session: Session = Depends(get_session)):
    """停止一个 Task 正在跑的 Job（如果有）。

    行为：
      - 找到该 Task 当前 status=='running' 的 Job
      - 给后台采集线程发出 cancel 事件
      - 采集循环每页/每篇都会检查，状态变成 'cancelled'
      - 返回被取消的 job_id；如果没在跑则返回 ok=False
    """
    from app.crawler.runner import request_cancel_job

    job = session.exec(
        select(Job)
        .where(Job.task_id == task_id, Job.status == "running")
        .order_by(Job.id.desc())
    ).first()
    if not job:
        return {"ok": False, "msg": "没有正在运行的 Job"}

    signaled = request_cancel_job(job.id)
    return {
        "ok": True,
        "signaled": signaled,
        "job_id": job.id,
        "msg": "已发出取消信号，采集循环将尽快停止",
    }


@router.get("/{task_id}/jobs", response_model=list[JobRead])
def list_jobs(task_id: int, session: Session = Depends(get_session)):
    return session.exec(select(Job).where(Job.task_id == task_id).order_by(Job.id.desc())).all()


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "job 不存在")
    return job
