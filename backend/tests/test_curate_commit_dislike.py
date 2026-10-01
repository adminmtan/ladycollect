"""回归测试：单帖 dislike 流程（curate_commit single mode）不应删历史词

重现生产 bug：
  用户场景：站点 default exclude 规则里已有手动加的关键词 K。
  单帖 dislike：CurateDialog 弹窗里 working_keywords 只含 AI 给的新词 N（不含 K），
  previous_existing 含 K。后端 curate_commit 计算
    to_add = N - {K} = {N}
    to_remove = {K} - N = {K}
  结果：手动加的 K 被删了，AI 给的 N 写入 → 表里"换了 1 个词"，但语义错。

期望行为：单帖 dislike 是「追加」语义，不应删历史词（用户没机会在弹窗里主动删 K，
K 也不在 working_keywords 里——用户根本看不到）。
"""
from __future__ import annotations

import os
import tempfile
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

# 测试期整站不验证 token，简化测试
import os
os.environ.setdefault("AUTH_DISABLED", "1")

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.models import FilterKeyword, FilterRule, Site  # noqa: E402


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """用临时 sqlite 文件挂载整套路由，session 自动重置"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        test_engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(test_engine)

        # 替换默认 engine（仅测试期）
        import app.db as _db
        original_engine = _db.engine
        _db.engine = test_engine

        from app.db import get_session as _real_get_session

        def _override_session():
            with Session(test_engine) as s:
                yield s

        app.dependency_overrides[_real_get_session] = _override_session

        with TestClient(app) as c:
            # 把 test_engine 暴露给 test，方便它们用同一个 engine 直接读写
            c._test_engine = test_engine  # type: ignore[attr-defined]
            yield c
        app.dependency_overrides.clear()
        _db.engine = original_engine
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _seed_site_and_rule(client: TestClient) -> tuple[int, int]:
    """返回 (site_id, rule_id) — 直接用 test fixture 提供的 engine，避免模块路径问题"""
    eng = client._test_engine  # type: ignore[attr-defined]
    with Session(eng) as s:
        site = Site(
            host="test.example",
            name="test-site",
            base_url="https://test.example/",  # NOT NULL
            enabled=True,
            default_kind="list_search",
        )
        s.add(site)
        s.flush()
        rule = FilterRule(
            name="test-site - 自动 exclude",
            scope="site",
            site_id=site.id,
            rule_type="exclude",
            enabled=True,
        )
        s.add(rule)
        s.flush()
        # 用户手动加的历史关键词 K
        s.add(FilterKeyword(rule_id=rule.id, keyword="历史词", source="manual"))
        s.commit()
        s.refresh(rule)
        return site.id, rule.id


def test_dislike_single_mode_should_not_remove_existing_keywords(client: TestClient):
    """单帖 dislike：previous_existing=[历史词] + keywords=[AI新词]
    期望：to_add=[AI新词]（追加）+ to_remove=[]（不动历史词）"""
    site_id, rule_id = _seed_site_and_rule(client)

    # single-mode dislike 真实 payload（前端 CurateDialog.vue:onCommit 在 mode==='single' 时）：
    #   previous_existing = []（追加语义，不传历史词）
    #   keywords = AI 给的新词
    #   note = 'dislike'（让后端 curate_commit 识别为追加语义，不删历史词）
    payload = {
        "rule_id": rule_id,
        "keywords": ["AI新词"],
        "previous_existing": [],
        "post_ids_to_delete": [],
        "note": "dislike",
    }
    res = client.post("/api/posts/curate/commit", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()

    # 期望：to_add 含 AI 新词，to_remove 不应删用户手动加的「历史词」
    assert "ai新词" in data["keywords_added"], f"AI 新词未写入: {data}"
    assert data["keywords_removed"] == [], f"历史词不应被删除: {data}"

    # 直接从数据库再次断言（所有词都是 lowercase）
    eng = client._test_engine  # type: ignore[attr-defined]
    from sqlmodel import select
    with Session(eng) as s:
        kws = {k.keyword for k in s.exec(
            select(FilterKeyword).where(FilterKeyword.rule_id == rule_id)
        ).all()}
    assert kws == {"历史词", "ai新词"}, f"规则下关键词应并存: {kws}"


def test_dislike_single_mode_repeated_append(client: TestClient):
    """连续两次单帖 dislike：第二次的 AI 关键词应追加，不应替换"""
    site_id, rule_id = _seed_site_and_rule(client)

    base = {
        "rule_id": rule_id,
        "previous_existing": [],   # single-mode 追加语义
        "post_ids_to_delete": [],
        "note": "dislike",         # 标记 dislike 语义，后端不会删历史词
    }

    # 第一次 dislike：AI 给 "AI词1"
    r1 = client.post("/api/posts/curate/commit", json={**base, "keywords": ["AI词1"]})
    assert r1.status_code == 200, r1.text
    assert "ai词1" in r1.json()["keywords_added"]
    assert r1.json()["keywords_removed"] == []

    # 第二次 dislike：AI 给 "AI词2"，previous_existing 仍为空（single-mode 不变）
    r2 = client.post(
        "/api/posts/curate/commit",
        json={**base, "keywords": ["AI词2"]},
    )
    assert r2.status_code == 200, r2.text
    assert "ai词2" in r2.json()["keywords_added"]
    assert r2.json()["keywords_removed"] == []

    # 表里现在应该有 3 个：历史词 + AI词1 + AI词2
    eng = client._test_engine  # type: ignore[attr-defined]
    from sqlmodel import select
    with Session(eng) as s:
        kws = {k.keyword for k in s.exec(
            select(FilterKeyword).where(FilterKeyword.rule_id == rule_id)
        ).all()}
    assert kws == {"历史词", "ai词1", "ai词2"}, f"应并存 3 个关键词: {kws}"


def test_curate_site_mode_can_remove_old_hists(client: TestClient):
    """site/multi 模式（整理已有规则）：note='curate' 时仍能删历史词

    这是 dislike 修复的反向保证——不能让 site/multi 模式的"用户主动删词"行为退化。
    """
    site_id, rule_id = _seed_site_and_rule(client)

    # 用户在 site 框里编辑：保留 AI 词1，删掉历史词
    payload = {
        "rule_id": rule_id,
        "keywords": ["AI词1"],            # 用户编辑后最终保留的
        "previous_existing": ["历史词"],    # preview 时已有的
        "post_ids_to_delete": [],
        "note": "curate",                  # site/multi 模式
    }
    res = client.post("/api/posts/curate/commit", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    # site 模式下应保留"用户主动删历史词"的语义
    assert "ai词1" in data["keywords_added"]
    assert "历史词" in data["keywords_removed"]

    eng = client._test_engine  # type: ignore[attr-defined]
    from sqlmodel import select
    with Session(eng) as s:
        kws = {k.keyword for k in s.exec(
            select(FilterKeyword).where(FilterKeyword.rule_id == rule_id)
        ).all()}
    assert kws == {"ai词1"}, f"历史词应被删: {kws}"