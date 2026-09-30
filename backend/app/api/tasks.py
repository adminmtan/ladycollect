"""采集任务 API"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import update as _update
from sqlmodel import Session, delete, select

from app.crawler.runner import run_task_sync
from app.db import get_session
from app.models import Job, Post, Site, Task, utcnow
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

    # 1) 先停掉正在跑的 job（如果有），避免与删除竞争
    running_jobs = session.exec(
        select(Job).where(Job.task_id == task_id, Job.status == "running")
    ).all()
    for j in running_jobs:
        j.status = "cancelled"
        j.finished_at = utcnow()
        session.add(j)
    if running_jobs:
        session.commit()
        logger.warning("delete_task: task_id=%d 取消 %d 个 running job", task_id, len(running_jobs))

    # 2) 把 Posts 解绑（task_id 置 NULL）—— Posts 是独立采集结果，不属于 Task 生命周期
    #    防止 posts.task_id 变成孤儿后，前端"按 task 过滤帖子"显示成空
    session.exec(
        _update(Post).where(Post.task_id == task_id).values(task_id=None)
    )

    # 3) 级联删 jobs —— 关键修复！
    #    之前只删 task，导致 jobs 表残留 task_id=已删ID 的孤儿行。
    #    下次新建 task 跑 job 时，SQLite 自增 ROWID 接着 max(ROWID)+1，
    #    用户看到新 task 的 jobs ID 续着上一个被删 task 的 ID，体验上像"延续"。
    orphan_jobs = session.exec(select(Job).where(Job.task_id == task_id)).all()
    orphan_ids = [j.id for j in orphan_jobs]
    session.exec(delete(Job).where(Job.task_id == task_id))

    # 4) 移除调度（如有）
    try:
        remove_task(task_id)
    except Exception as e:
        logger.warning("移除调度失败：%s", e)

    # 5) 最后删 task 本身
    session.delete(task)
    session.commit()

    logger.info(
        "delete_task: task_id=%d 清理完成（orphan_jobs=%d, posts_unbind=全部关联 posts.task_id→NULL）",
        task_id, len(orphan_ids),
    )
    return {"ok": True, "deleted_jobs": len(orphan_ids)}


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
      - 立即把 job.status 写成 'cancelled'（即使采集线程还没响应 cancel_ev，
        前端下一次 fetch 也会立刻看到按钮切回「启动」）
      - 采集循环每页/每篇都会检查，状态确认变成 'cancelled'
      - 返回被取消的 job_id；如果没在跑则返回 ok=False
    """
    from datetime import datetime, timezone as _tz
    from app.crawler.runner import request_cancel_job

    job = session.exec(
        select(Job)
        .where(Job.task_id == task_id, Job.status == "running")
        .order_by(Job.id.desc())
    ).first()
    if not job:
        return {"ok": False, "msg": "没有正在运行的 Job"}

    signaled = request_cancel_job(job.id)
    # 立刻写 cancelled：UI 能在下一次 3s 轮询内看到按钮切回「启动」，
    # 采集线程后续即使检测到 status 已 cancelled 也会快速退出。
    job.status = "cancelled"
    if not job.finished_at:
        job.finished_at = datetime.now(_tz.utc)
    if not job.error:
        job.error = "用户手动取消"
    session.add(job)
    session.commit()

    return {
        "ok": True,
        "signaled": signaled,
        "job_id": job.id,
        "msg": "已停止（采集循环将在 30s 内彻底退出）",
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
