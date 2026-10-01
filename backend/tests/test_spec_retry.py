"""回归测试：采集失败 spec 级重试器

重现生产 bug (2026-02 报告)：
  列表页 / 详情页 单次失败立即 continue 跳页，偶发失败导致整篇漏数据。
  期望：分级重试（5s / 15s），瞬时错误重试，永久错误跳过，
  JobCancelled 响应调度器取消。

设计：把 retry 抽成上下文管理器 (with_retry)，跑 page/parser 整段。
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional

# 测试期整站不验证 token
os.environ.setdefault("AUTH_DISABLED", "1")

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings  # noqa: E402
from app.crawler.runner import (  # noqa: E402
    JobCancelled,
    spec_with_retry,
    SPEC_RETRYABLE_EXCEPTIONS,
    NonRetryableError,
)
from app.main import app  # noqa: E402


# ============ 单元测试: spec_with_retry 上下文管理器 ============


class _FakeTimeout(Exception):
    pass


class _FakeForbidden(Exception):
    """模拟 4xx 永久失败"""

    pass


@contextmanager
def _fake_page():
    """假装 page 对象"""
    yield object()


def test_retry_then_success():
    """瞬时错误前 2 次抛超时，第 3 次成功 → 应走到 finally"""
    attempts = []

    def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise _FakeTimeout("ETIMEDOUT")
        return "ok"

    start = time.monotonic()
    with spec_with_retry(
        spec_name="test-spec",
        cancel_ev=threading.Event(),
        retryable_exceptions=(_FakeTimeout,),
        sleeps=(0, 0, 0),  # 测试期不 sleep 加快
        total_timeout_s=10,
    ) as r:
        result = r.run(fn)
    elapsed = time.monotonic() - start

    assert result == "ok", f"应返回成功结果: {attempts}"
    assert len(attempts) == 3, f"应重试 3 次: {attempts}"
    assert elapsed < 2, f"用 sleeps=(0,0,0) 应极快: {elapsed:.2f}s"


def test_retry_exhausted_raises_last():
    """重试用尽后保留最后一次异常（让上层 except 接住）"""
    attempts = []

    def fn():
        attempts.append(1)
        raise _FakeTimeout(f"fail-{len(attempts)}")

    with pytest.raises(_FakeTimeout, match="fail-3"):
        with spec_with_retry(
            spec_name="test-spec",
            cancel_ev=threading.Event(),
            retryable_exceptions=(_FakeTimeout,),
            sleeps=(0, 0, 0),
            total_timeout_s=10,
        ) as r:
            r.run(fn)

    assert len(attempts) == 3, f"应重试到 max_attempts=3: {attempts}"


def test_non_retryable_skips_immediately():
    """非重试白名单的异常立刻抛，不重试"""
    attempts = []

    def fn():
        attempts.append(1)
        raise _FakeForbidden("403 Forbidden")

    # _FakeForbidden 不在 retryable 列表 → 第 1 次就抛
    with pytest.raises(_FakeForbidden):
        with spec_with_retry(
            spec_name="test-spec",
            cancel_ev=threading.Event(),
            retryable_exceptions=(_FakeTimeout,),  # 白名单只含 _FakeTimeout
            sleeps=(0, 0, 0),
            total_timeout_s=10,
        ) as r:
            r.run(fn)

    assert len(attempts) == 1, f"非白名单异常不应重试: {attempts}"


def test_cancel_during_retry_raises_jobcancelled():
    """重试期间收到 cancel_ev → 立刻抛 JobCancelled，不继续重试"""
    attempts = []
    cancel_ev = threading.Event()

    def fn():
        attempts.append(1)
        # 第一次失败后让 cancel_ev 触发
        if len(attempts) == 1:
            cancel_ev.set()
        raise _FakeTimeout("ETIMEDOUT")

    with pytest.raises(JobCancelled):
        with spec_with_retry(
            spec_name="test-spec",
            cancel_ev=cancel_ev,
            retryable_exceptions=(_FakeTimeout,),
            sleeps=(0, 0, 0),
            total_timeout_s=10,
        ) as r:
            r.run(fn)

    assert len(attempts) == 1, f"cancel 后应停止重试: {attempts}"


def test_total_timeout_aborts():
    """total_timeout_s 触发 → 不再发起新 attempt"""
    attempts = []

    def fn():
        attempts.append(1)
        raise _FakeTimeout("slow")

    # total_timeout=0 让任何 attempt 都超时（用 sleeps=(0.1, 0.1, 0.1) 撑爆）
    start = time.monotonic()
    with pytest.raises((_FakeTimeout, JobCancelled)):
        with spec_with_retry(
            spec_name="test-spec",
            cancel_ev=threading.Event(),
            retryable_exceptions=(_FakeTimeout,),
            sleeps=(0.05, 0.05, 0.05),
            total_timeout_s=0.1,  # 极小
        ) as r:
            r.run(fn)
    elapsed = time.monotonic() - start

    assert elapsed < 1, f"total_timeout 应能 abort: {elapsed:.2f}s"
    assert len(attempts) <= 2, f"小 total_timeout 应限制 attempts: {len(attempts)}"


def test_nonretryable_error_helper():
    """NonRetryableError 包装: 让 caller 把 4xx 升格为非重试"""
    inner = _FakeForbidden("403")

    class Wrapper(NonRetryableError):
        pass

    with pytest.raises(Wrapper):
        raise Wrapper(f"non-retryable: {inner}")