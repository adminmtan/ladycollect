"""/api/settings：应用运行时配置（AI 关键词提取）

GET    /api/settings           列表（带掩码、来源、提示文案）
PUT    /api/settings/{key}     单项写入（value=空字符串 -> 删除 -> 回退默认）
POST   /api/settings/test      测试当前/临时 AI 连接（chat/completions ping）
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException

from app.config import settings as env_settings  # noqa: E402
from app.schemas import (  # noqa: E402
    AppSettingRead,
    AppSettingTestRequest,
    AppSettingTestResponse,
    AppSettingUpdate,
)
from app.services.settings import (  # noqa: E402
    SETTING_DEFS,
    get_all_settings_for_api,
    get_setting,
    set_setting,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=list[AppSettingRead])
def list_settings():
    """返回所有可配置项。api_key 永远是掩码。"""
    # 用 services 里的元信息构造，但 response_model 需要 AppSettingRead；
    # 多余字段（label/description/placeholder）通过 model_config 允许 extras。
    raw = get_all_settings_for_api()
    # 转换：AppSettingRead 只用 key/value/masked/source/updated_at
    from app.schemas import AppSettingRead
    return [
        AppSettingRead(
            key=r["key"],
            value=r["value"],
            masked=r["masked"],
            source=r["source"],
            updated_at=r.get("updated_at"),
        )
        for r in raw
    ]


@router.get("/_meta")
def list_settings_meta():
    """返回配置项的展示信息（label/description/placeholder），用于前端表单生成"""
    return get_all_settings_for_api()


@router.put("/{key}", response_model=AppSettingRead)
def update_setting(key: str, payload: AppSettingUpdate):
    if key not in SETTING_DEFS:
        raise HTTPException(404, f"未知配置项：{key}")
    set_setting(key, payload.value)
    # 回读
    value, source, _ = get_setting(key)
    from app.schemas import AppSettingRead
    from app.services.settings import _mask
    definition = SETTING_DEFS[key]
    api_value = _mask(key, value) if definition.get("sensitive") else value
    _, updated_at = (
        __import__("app.services.settings", fromlist=["_read_db_value"])._read_db_value(key)
    )
    return AppSettingRead(
        key=key,
        value=api_value,
        masked=bool(definition.get("sensitive")),
        source=source,
        updated_at=updated_at,
    )


@router.post("/test", response_model=AppSettingTestResponse)
def test_ai_connection(payload: AppSettingTestRequest):
    """用提交的值（或已存的值）ping 一下 chat/completions。

    - 全部为空时直接返回 ok=False（未配置）
    - 单条缺失则报具体哪个缺失
    """
    base_url = payload.base_url if payload.base_url is not None else get_setting("openai_base_url")[0]
    api_key = payload.api_key if payload.api_key is not None else get_setting("openai_api_key")[0]
    model = payload.model if payload.model is not None else get_setting("openai_model")[0]
    timeout = payload.timeout if payload.timeout is not None else int(get_setting("openai_timeout")[0] or "20")

    if not base_url:
        return AppSettingTestResponse(ok=False, message="缺少 API Base URL")
    if not api_key:
        return AppSettingTestResponse(ok=False, message="缺少 API Key（保存后再测试）")
    if not model:
        return AppSettingTestResponse(ok=False, message="缺少模型名")

    t0 = time.time()
    try:
        import json as _json
        import ssl
        import urllib.error
        import urllib.request

        # 优先用 certifi 的 CA bundle；homebrew python 经常找不到系统 CA 证书
        ssl_ctx = ssl.create_default_context()
        try:
            import certifi
            ssl_ctx.load_verify_locations(certifi.where())
        except Exception:
            pass
        try:
            ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        except AttributeError:
            pass

        req_body = _json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
            "temperature": 0,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=req_body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            latency = int((time.time() - t0) * 1000)
            snippet = ""
            try:
                snippet = (e.read().decode("utf-8", errors="replace") or "")[:300]
            except Exception:
                pass
            return AppSettingTestResponse(
                ok=False,
                message=f"HTTP {e.code}：{snippet or e.reason}",
                latency_ms=latency,
            )
        except urllib.error.URLError as e:
            latency = int((time.time() - t0) * 1000)
            return AppSettingTestResponse(
                ok=False,
                message=f"网络异常：{e.reason}",
                latency_ms=latency,
            )

        latency = int((time.time() - t0) * 1000)
        if status != 200:
            return AppSettingTestResponse(
                ok=False,
                message=f"HTTP {status}：{body[:300]}",
                latency_ms=latency,
            )

        data = _json.loads(body) if body else {}
        reply = ""
        try:
            reply = (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        except Exception:
            pass
        return AppSettingTestResponse(
            ok=True,
            message="连接成功",
            latency_ms=latency,
            model_reply=reply[:120] or None,
        )
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        return AppSettingTestResponse(
            ok=False,
            message=f"调用异常：{e}",
            latency_ms=latency,
        )
