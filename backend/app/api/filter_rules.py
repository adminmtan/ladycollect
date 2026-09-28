"""智能过滤规则 CRUD API

路由：
- GET    /api/filter-rules          列表（按 site_id / scope / rule_type 过滤）
- POST   /api/filter-rules          创建规则（含初始 keywords）
- GET    /api/filter-rules/{id}     详情（含完整 keywords）
- PATCH  /api/filter-rules/{id}     更新（启停、改名、改 scope 等）
- DELETE /api/filter-rules/{id}     删除
- POST   /api/filter-rules/{id}/keywords  追加关键词（手动）
- DELETE /api/filter-rules/{id}/keywords/{kid}  删除单个关键词
"""
from __future__ import annotations

import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func

from app.db import get_session
from app.models import FilterKeyword, FilterRule, Site
from app.schemas import (
    FilterKeywordCreate,
    FilterKeywordRead,
    FilterRuleCreate,
    FilterRuleRead,
    FilterRuleSummary,
    FilterRuleUpdate,
)
from app.crawler.runner import invalidate_filter_rules_cache

router = APIRouter(prefix="/api/filter-rules", tags=["filter-rules"])


def _clean_keyword(kw: str) -> str:
    if not kw:
        return ""
    k = kw.strip().lower()
    k = re.sub(r"^[\s,，.。:：;；、/\-_()()【】\[\]「」『』]+", "", k)
    k = re.sub(r"[\s,，.。:：;；、/\-_()()【】\[\]「」『』]+$", "", k)
    return k


def _validate_scope_type(scope: str, site_id: Optional[int], rule_type: str) -> None:
    if scope not in ("site", "global"):
        raise HTTPException(400, "scope 必须为 site 或 global")
    if rule_type not in ("exclude", "include", "tag"):
        raise HTTPException(400, "rule_type 必须为 exclude / include / tag")
    if scope == "site" and site_id is None:
        raise HTTPException(400, "scope=site 时 site_id 必填")
    if scope == "global" and site_id is not None:
        raise HTTPException(400, "scope=global 时 site_id 必须为空")


def _to_summary(rule: FilterRule, keyword_count: int, hit_count_total: int) -> FilterRuleSummary:
    return FilterRuleSummary(
        id=rule.id,
        name=rule.name,
        scope=rule.scope,
        site_id=rule.site_id,
        rule_type=rule.rule_type,
        enabled=rule.enabled,
        note=rule.note,
        keyword_count=keyword_count,
        hit_count_total=hit_count_total,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _to_read(rule: FilterRule, keywords: list[FilterKeyword]) -> FilterRuleRead:
    return FilterRuleRead(
        id=rule.id,
        name=rule.name,
        scope=rule.scope,
        site_id=rule.site_id,
        rule_type=rule.rule_type,
        enabled=rule.enabled,
        note=rule.note,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        keyword_count=len(keywords),
        keywords=[FilterKeywordRead.model_validate(k) for k in keywords],
    )


@router.get("", response_model=list[FilterRuleSummary])
def list_filter_rules(
    site_id: Optional[int] = None,
    scope: Optional[str] = None,
    rule_type: Optional[str] = None,
    enabled: Optional[bool] = None,
    session: Session = Depends(get_session),
):
    """列出过滤规则（含每个规则的关键词数 + 总命中数）"""
    q = select(FilterRule)
    if site_id is not None:
        q = q.where(FilterRule.site_id == site_id)
    if scope:
        q = q.where(FilterRule.scope == scope)
    if rule_type:
        q = q.where(FilterRule.rule_type == rule_type)
    if enabled is not None:
        q = q.where(FilterRule.enabled == enabled)
    q = q.order_by(FilterRule.id.desc())
    rules = session.exec(q).all()

    if not rules:
        return []

    # 一次 SQL 拿到全部 keywords 统计
    rule_ids = [r.id for r in rules]
    rows = session.exec(
        select(
            FilterKeyword.rule_id,
            func.count(FilterKeyword.id),
            func.coalesce(func.sum(FilterKeyword.hit_count), 0),
        )
        .where(FilterKeyword.rule_id.in_(rule_ids))
        .group_by(FilterKeyword.rule_id)
    ).all()
    stat = {rid: (cnt, hits) for rid, cnt, hits in rows}

    return [_to_summary(r, *stat.get(r.id, (0, 0))) for r in rules]


@router.post("", response_model=FilterRuleRead)
def create_filter_rule(payload: FilterRuleCreate, session: Session = Depends(get_session)):
    """创建规则 + 可选初始关键词"""
    _validate_scope_type(payload.scope, payload.site_id, payload.rule_type)

    if payload.scope == "site" and payload.site_id is not None:
        if not session.get(Site, payload.site_id):
            raise HTTPException(404, "site 不存在")

    rule = FilterRule(
        name=payload.name,
        scope=payload.scope,
        site_id=payload.site_id,
        rule_type=payload.rule_type,
        enabled=payload.enabled,
        note=payload.note,
    )
    session.add(rule)
    session.flush()  # 取 id

    # 关键词去重入库
    seen: set[str] = set()
    for kw in payload.keywords or []:
        k = _clean_keyword(kw)
        if not k or k in seen:
            continue
        seen.add(k)
        session.add(FilterKeyword(rule_id=rule.id, keyword=k, source="manual"))
    session.commit()

    keywords = session.exec(
        select(FilterKeyword).where(FilterKeyword.rule_id == rule.id)
    ).all()
    return _to_read(rule, list(keywords))


@router.get("/{rule_id}", response_model=FilterRuleRead)
def get_filter_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(FilterRule, rule_id)
    if not rule:
        raise HTTPException(404, "rule 不存在")
    keywords = session.exec(
        select(FilterKeyword)
        .where(FilterKeyword.rule_id == rule_id)
        .order_by(FilterKeyword.id.desc())
    ).all()
    return _to_read(rule, list(keywords))


@router.patch("/{rule_id}", response_model=FilterRuleRead)
def update_filter_rule(rule_id: int, payload: FilterRuleUpdate, session: Session = Depends(get_session)):
    rule = session.get(FilterRule, rule_id)
    if not rule:
        raise HTTPException(404, "rule 不存在")

    data = payload.model_dump(exclude_unset=True)

    # scope / site_id 联合校验
    new_scope = data.get("scope", rule.scope)
    new_site_id = data.get("site_id", rule.site_id)
    new_rule_type = data.get("rule_type", rule.rule_type)
    if "scope" in data or "site_id" in data or "rule_type" in data:
        _validate_scope_type(new_scope, new_site_id, new_rule_type)

    for k, v in data.items():
        setattr(rule, k, v)
    session.add(rule)
    session.commit()
    session.refresh(rule)

    # 缓存失效（让下次采集用上新配置）
    if rule.scope == "global":
        invalidate_filter_rules_cache(None)
    elif rule.site_id is not None:
        invalidate_filter_rules_cache(rule.site_id)

    keywords = session.exec(
        select(FilterKeyword).where(FilterKeyword.rule_id == rule_id).order_by(FilterKeyword.id.desc())
    ).all()
    return _to_read(rule, list(keywords))


@router.delete("/{rule_id}")
def delete_filter_rule(rule_id: int, session: Session = Depends(get_session)):
    rule = session.get(FilterRule, rule_id)
    if not rule:
        raise HTTPException(404, "rule 不存在")
    scope = rule.scope
    site_id = rule.site_id
    session.delete(rule)
    session.commit()
    if scope == "global":
        invalidate_filter_rules_cache(None)
    elif site_id is not None:
        invalidate_filter_rules_cache(site_id)
    return {"ok": True}


@router.post("/{rule_id}/keywords", response_model=list[FilterKeywordRead])
def add_keywords(rule_id: int, payload: FilterKeywordCreate, session: Session = Depends(get_session)):
    """追加关键词（手动添加；source 默认为 manual）"""
    rule = session.get(FilterRule, rule_id)
    if not rule:
        raise HTTPException(404, "rule 不存在")

    # 已存在的关键词，避免重复
    existing = {
        k.keyword
        for k in session.exec(select(FilterKeyword).where(FilterKeyword.rule_id == rule_id)).all()
    }
    added: list[FilterKeyword] = []
    for kw in payload.keywords or []:
        k = _clean_keyword(kw)
        if not k or k in existing:
            continue
        existing.add(k)
        kw_obj = FilterKeyword(rule_id=rule_id, keyword=k, source="manual")
        session.add(kw_obj)
        added.append(kw_obj)
    session.commit()

    # 失效缓存
    if rule.scope == "global":
        invalidate_filter_rules_cache(None)
    elif rule.site_id is not None:
        invalidate_filter_rules_cache(rule.site_id)

    for k in added:
        session.refresh(k)
    return [FilterKeywordRead.model_validate(k) for k in added]


@router.delete("/{rule_id}/keywords/{keyword_id}")
def delete_keyword(rule_id: int, keyword_id: int, session: Session = Depends(get_session)):
    kw = session.get(FilterKeyword, keyword_id)
    if not kw or kw.rule_id != rule_id:
        raise HTTPException(404, "keyword 不存在")
    rule = session.get(FilterRule, rule_id)
    session.delete(kw)
    session.commit()

    if rule is not None:
        if rule.scope == "global":
            invalidate_filter_rules_cache(None)
        elif rule.site_id is not None:
            invalidate_filter_rules_cache(rule.site_id)

    return {"ok": True}
