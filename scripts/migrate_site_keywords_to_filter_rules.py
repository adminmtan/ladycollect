"""一次性迁移：sites.title_include_keywords / title_exclude_keywords → filter_rules + filter_keywords

逻辑：
- 对每个 site：
  - 把 title_include_keywords 合并为一条 FilterRule（scope=site, rule_type=include）
  - 把 title_exclude_keywords 合并为一条 FilterRule（scope=site, rule_type=exclude）
  - 跳过空集
- 已存在同名规则时：跳过创建规则，把关键词追加进去（去重）
- 迁移完成后把 sites.title_include_keywords / title_exclude_keywords 置为 '[]'（列保留，不删）

可重入：重复执行不会重复创建。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 让脚本能从项目根目录 import app
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from sqlmodel import Session, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import FilterKeyword, FilterRule, Site  # noqa: E402
from sqlalchemy import text  # noqa: E402


def _kw_iter(raw):
    """解析 sites.title_*_keywords 字段（可能是 list 或 JSON 字符串）"""
    if raw is None:
        return
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                items = parsed
            else:
                items = [raw]
        except Exception:
            items = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        return
    for s in items:
        if s is None:
            continue
        k = str(s).strip()
        if k:
            yield k


def _ensure_rule(session: Session, site: Site, rule_type: str) -> FilterRule | None:
    """找到或创建一条 site-scope 同 rule_type 规则"""
    existing = session.exec(
        select(FilterRule).where(
            FilterRule.scope == "site",
            FilterRule.site_id == site.id,
            FilterRule.rule_type == rule_type,
        )
    ).all()
    if existing:
        # 已存在：直接复用第一条（用户可能手动建过）
        return existing[0]
    rule_name = f"{site.name} {rule_type}（迁移自站点配置）"
    rule = FilterRule(
        name=rule_name,
        scope="site",
        site_id=site.id,
        rule_type=rule_type,
        enabled=True,
        note="迁移自 sites.title_include/exclude_keywords",
    )
    session.add(rule)
    session.flush()
    return rule


def _attach_keywords(session: Session, rule: FilterRule, keywords: list[str]) -> int:
    """把关键词写入 rule（去重）。返回实际新增条数"""
    existing_kws = session.exec(
        select(FilterKeyword).where(FilterKeyword.rule_id == rule.id)
    ).all()
    have = {(k.keyword or "").strip().lower() for k in existing_kws}
    added = 0
    for kw in keywords:
        norm = kw.strip().lower()
        if not norm or norm in have:
            continue
        session.add(
            FilterKeyword(
                rule_id=rule.id,
                keyword=norm,
                source="manual",
                weight=1.0,
                hit_count=0,
            )
        )
        have.add(norm)
        added += 1
    return added


def main() -> int:
    print("[migrate] 开始迁移 sites.title_*_keywords → filter_rules")
    sites_done = 0
    rules_created = 0
    rules_existing = 0
    kws_added = 0
    with Session(engine) as session:
        sites = session.exec(select(Site)).all()
        print(f"[migrate] 找到 {len(sites)} 个站点")
        for site in sites:
            incs = list(_kw_iter(site.title_include_keywords))
            excs = list(_kw_iter(site.title_exclude_keywords))
            if not incs and not excs:
                continue
            sites_done += 1
            for kw_list, rt in ((incs, "include"), (excs, "exclude")):
                if not kw_list:
                    continue
                # 判断是新建还是复用
                existing_count = len(
                    session.exec(
                        select(FilterRule).where(
                            FilterRule.scope == "site",
                            FilterRule.site_id == site.id,
                            FilterRule.rule_type == rt,
                        )
                    ).all()
                )
                rule = _ensure_rule(session, site, rt)
                if existing_count == 0:
                    rules_created += 1
                else:
                    rules_existing += 1
                added = _attach_keywords(session, rule, kw_list)
                kws_added += added
                print(
                    f"  site#{site.id} {site.name} [{rt}] "
                    f"+{added} kw / {len(kw_list)} total"
                )
            # 清空站点表字段（保留列）
            session.exec(
                text(
                    "UPDATE sites SET title_include_keywords='[]', "
                    "title_exclude_keywords='[]' WHERE id=:sid"
                ),
                params={"sid": site.id},
            )
        session.commit()
    print(
        f"[migrate] 完成：sites={sites_done} rules_new={rules_created} "
        f"rules_existing={rules_existing} kws_added={kws_added}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
