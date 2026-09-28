"""用户反馈 / 智能学习 API

核心流程：标记「不喜欢」一篇帖子 → 自动学习关键词 → 写入站点级 filter_rule → 删除帖子
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, or_, select

from app.db import get_session
from app.learning import get_extractor
from app.models import FilterKeyword, FilterRule, Post, UserFeedback, utcnow
from app.schemas import (
    DislikeRequest,
    DislikeResponse,
    LikeRequest,
    LikeResponse,
    UserFeedbackRead,
)
from app.crawler.runner import invalidate_filter_rules_cache

router = APIRouter(prefix="/api", tags=["feedback"])


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


def _get_or_create_default_rule(
    session: Session,
    *,
    site_id: int,
    rule_type: str,
    rule_name_prefix: str,
) -> FilterRule:
    """获取/创建某个站点的默认规则

    命名约定：站点级「默认 exclude/include」规则名字固定为
    "<site.name> - 默认 exclude" 之类，便于前端查找。
    """
    # 找当前站点的 enabled 同类型规则（不限定名字，取第一条作为「默认」）
    rule = session.exec(
        select(FilterRule)
        .where(
            FilterRule.scope == "site",
            FilterRule.site_id == site_id,
            FilterRule.rule_type == rule_type,
        )
        .order_by(FilterRule.id.asc())
    ).first()

    if rule:
        return rule

    # 没找到就建一个
    from app.models import Site as _Site

    site = session.get(_Site, site_id)
    if not site:
        raise HTTPException(404, "site 不存在")

    rule = FilterRule(
        name=f"{site.name} - {rule_name_prefix}",
        scope="site",
        site_id=site_id,
        rule_type=rule_type,
        enabled=True,
        note="由用户反馈自动创建的默认规则",
    )
    session.add(rule)
    session.flush()
    return rule


def _persist_keywords(
    session: Session,
    *,
    rule_id: int,
    keywords: list[str],
    source: str,
) -> list[str]:
    """把关键词去重写入 filter_keywords；返回真正新增的（不包含已存在的）"""
    if not keywords:
        return []
    existing = {
        k.keyword
        for k in session.exec(
            select(FilterKeyword).where(FilterKeyword.rule_id == rule_id)
        ).all()
    }
    added: list[str] = []
    for k in keywords:
        k_norm = (k or "").strip().lower()
        if not k_norm or k_norm in existing:
            continue
        existing.add(k_norm)
        session.add(
            FilterKeyword(
                rule_id=rule_id,
                keyword=k_norm,
                source=source,
                weight=0.9 if source == "learned" else 0.8,
            )
        )
        added.append(k_norm)
    return added


def _record_feedback(
    session: Session,
    *,
    post: Optional[Post],
    title: str,
    site_id: Optional[int],
    action: str,
    keywords: list[str],
    rule_id: int,
    rule_type: str,
    note: Optional[str] = None,
) -> UserFeedback:
    fb = UserFeedback(
        post_id=post.id if post else None,
        site_id=site_id,
        title=title[:500],
        action=action,
        keywords_extracted=keywords,
        rule_id=rule_id,
        rule_type=rule_type,
        note=note,
    )
    session.add(fb)
    session.flush()
    return fb


def _load_post_or_404(post_id: int, session: Session) -> Post:
    p = session.get(Post, post_id)
    if not p:
        raise HTTPException(404, "post 不存在")
    return p


@router.post("/posts/{post_id}/dislike", response_model=DislikeResponse)
def dislike_post(
    post_id: int,
    payload: Optional[DislikeRequest] = None,
    session: Session = Depends(get_session),
):
    """用户标记「不喜欢」这篇帖子。

    行为：
    1. 加载 post，取其 site 与 title
    2. 找到/创建该站点的默认 exclude 规则
    3. 调用 AI 提取器（或本地降级）从 title 中提取关键词
    4. 关键词写入 filter_keywords（source=user_dislike）
    5. 写入 user_feedback 记录
    6. 删除该 post（立即从列表消失）
    7. 返回 { ok, rule_id, rule_name, keywords_added, extractor }
    """
    post = _load_post_or_404(post_id, session)
    title = post.title or ""
    site_id = post.site_id

    # 1) 取/建默认规则
    if payload and payload.rule_id:
        rule = session.get(FilterRule, payload.rule_id)
        if not rule:
            raise HTTPException(404, "指定 rule_id 不存在")
        if rule.rule_type != "exclude":
            raise HTTPException(400, "dislike 只能归类到 rule_type=exclude 的规则")
    else:
        rule = _get_or_create_default_rule(
            session, site_id=site_id, rule_type="exclude", rule_name_prefix="自动学习 exclude"
        )

    # 2) AI / 本地提取关键词
    # 取最近该站点的若干 dislike 历史标题一起喂给 AI（冷启动时只有当前一篇）
    history_titles = [
        fb.title
        for fb in session.exec(
            select(UserFeedback)
            .where(
                UserFeedback.site_id == site_id,
                UserFeedback.action == "dislike",
                UserFeedback.id != -1,  # 排除当前（尚未 commit）
            )
            .order_by(UserFeedback.id.desc())
            .limit(10)
        ).all()
    ]
    titles_for_ai = list({title, *history_titles})[:10]

    extractor = get_extractor()
    keywords, source = extractor.extract(titles_for_ai, action="dislike", top_n=8)

    # 3) 入库关键词
    added = _persist_keywords(
        session, rule_id=rule.id, keywords=keywords, source="user_dislike"
    )

    # 4) 写 feedback
    _record_feedback(
        session,
        post=post,
        title=title,
        site_id=site_id,
        action="dislike",
        keywords=keywords,
        rule_id=rule.id,
        rule_type="exclude",
        note=f"extractor={source}",
    )

    # 5) 删除 post
    session.delete(post)
    session.commit()
    session.refresh(rule)

    # 6) 失效规则缓存（让下次采集立刻使用新关键词）
    invalidate_filter_rules_cache(site_id)

    return DislikeResponse(
        ok=True,
        rule_id=rule.id,
        rule_name=rule.name,
        keywords_added=added,
        extractor=source,
        post_deleted=True,
    )


@router.post("/posts/{post_id}/like", response_model=LikeResponse)
def like_post(
    post_id: int,
    payload: Optional[LikeRequest] = None,
    session: Session = Depends(get_session),
):
    """用户标记「喜欢」→ 关键词进入 include 规则池（不删除帖子）

    与 dislike 的区别：
    - rule_type = include
    - 不删除帖子（用户希望保留更多这类内容）
    """
    post = _load_post_or_404(post_id, session)
    title = post.title or ""
    site_id = post.site_id

    if payload and payload.rule_id:
        rule = session.get(FilterRule, payload.rule_id)
        if not rule:
            raise HTTPException(404, "指定 rule_id 不存在")
        if rule.rule_type != "include":
            raise HTTPException(400, "like 只能归类到 rule_type=include 的规则")
    else:
        rule = _get_or_create_default_rule(
            session, site_id=site_id, rule_type="include", rule_name_prefix="自动学习 include"
        )

    history_titles = [
        fb.title
        for fb in session.exec(
            select(UserFeedback)
            .where(
                UserFeedback.site_id == site_id,
                UserFeedback.action == "like",
            )
            .order_by(UserFeedback.id.desc())
            .limit(10)
        ).all()
    ]
    titles_for_ai = list({title, *history_titles})[:10]

    extractor = get_extractor()
    keywords, source = extractor.extract(titles_for_ai, action="like", top_n=8)

    added = _persist_keywords(
        session, rule_id=rule.id, keywords=keywords, source="user_like"
    )

    _record_feedback(
        session,
        post=post,
        title=title,
        site_id=site_id,
        action="like",
        keywords=keywords,
        rule_id=rule.id,
        rule_type="include",
        note=f"extractor={source}",
    )

    session.commit()
    session.refresh(rule)

    # 失效规则缓存
    invalidate_filter_rules_cache(site_id)

    return LikeResponse(
        ok=True,
        rule_id=rule.id,
        rule_name=rule.name,
        keywords_added=added,
        extractor=source,
        post_deleted=False,
    )


@router.get("/feedback", response_model=list[UserFeedbackRead])
def list_feedback(
    site_id: Optional[int] = None,
    action: Optional[str] = None,
    rule_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    """查看反馈历史（按时间倒序）"""
    q = select(UserFeedback)
    if site_id is not None:
        q = q.where(UserFeedback.site_id == site_id)
    if action:
        q = q.where(UserFeedback.action == action)
    if rule_id is not None:
        q = q.where(UserFeedback.rule_id == rule_id)
    q = q.order_by(UserFeedback.id.desc()).limit(limit)
    rows = session.exec(q).all()
    out: list[UserFeedbackRead] = []
    for r in rows:
        out.append(
            UserFeedbackRead(
                id=r.id,
                post_id=r.post_id,
                site_id=r.site_id,
                title=r.title,
                action=r.action,
                keywords_extracted=_to_list(r.keywords_extracted),
                rule_id=r.rule_id,
                rule_type=r.rule_type,
                note=r.note,
                created_at=r.created_at,
            )
        )
    return out
