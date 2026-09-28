"""统计 API"""
from __future__ import annotations

from datetime import date as date_t, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session, func, select

from app.db import get_session
from app.models import Job, Post, Site, Task

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview")
def overview(session: Session = Depends(get_session)):
    total_posts = session.exec(select(func.count(Post.id))).one()
    total_sites = session.exec(select(func.count(Site.id))).one()
    total_tasks = session.exec(select(func.count(Task.id))).one()
    total_jobs = session.exec(select(func.count(Job.id))).one()

    today = date_t.today()
    seven_days_ago = today - timedelta(days=7)
    recent_posts = session.exec(
        select(func.count(Post.id)).where(Post.created_at >= datetime.combine(seven_days_ago, datetime.min.time()))
    ).one()

    # 含 magnet/ed2k 的帖子数
    all_posts = session.exec(select(Post)).all()
    import json

    with_magnet = 0
    with_ed2k = 0
    for p in all_posts:
        mags = p.magnet if isinstance(p.magnet, list) else (json.loads(p.magnet) if isinstance(p.magnet, str) and p.magnet else [])
        ed2s = p.ed2k if isinstance(p.ed2k, list) else (json.loads(p.ed2k) if isinstance(p.ed2k, str) and p.ed2k else [])
        if mags:
            with_magnet += 1
        if ed2s:
            with_ed2k += 1

    return {
        "total_posts": total_posts,
        "with_magnet": with_magnet,
        "with_ed2k": with_ed2k,
        "total_sites": total_sites,
        "total_tasks": total_tasks,
        "total_jobs": total_jobs,
        "recent_posts_7d": recent_posts,
    }


@router.get("/recent-jobs")
def recent_jobs(limit: int = 10, session: Session = Depends(get_session)):
    return session.exec(select(Job).order_by(Job.id.desc()).limit(limit)).all()
