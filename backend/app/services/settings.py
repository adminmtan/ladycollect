"""应用运行时配置服务

持久化在 app_settings 表（key/value）。读取优先级：
  app_settings 表 > .env / 环境变量 > 字段默认值

API key 永远以掩码形式返回（明文仅在写入时使用）。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlmodel import Session, select

from app.config import settings as env_settings
from app.db import engine
from app.models import AppSetting

logger = logging.getLogger(__name__)


# 配置项元信息（key / 默认 / 是否敏感 / 标签 / 描述）
SETTING_DEFS: dict[str, dict] = {
    "openai_base_url": {
        "default": env_settings.openai_base_url,
        "sensitive": False,
        "label": "API Base URL",
        "description": "OpenAI 兼容服务的根地址（不含 /chat/completions）。支持 OpenAI / DeepSeek / Azure / Ollama / 自建网关。",
        "placeholder": "https://api.openai.com/v1",
    },
    "openai_api_key": {
        "default": env_settings.openai_api_key or "",
        "sensitive": True,
        "label": "API Key",
        "description": "Bearer Token。留空表示关闭 AI 提取（自动降级到本地规则）。",
        "placeholder": "sk-...",
    },
    "openai_model": {
        "default": env_settings.openai_model,
        "sensitive": False,
        "label": "模型",
        "description": "对话模型 ID，例如 gpt-4o-mini / deepseek-chat / qwen-turbo 等。",
        "placeholder": "gpt-4o-mini",
    },
    "openai_timeout": {
        "default": str(env_settings.openai_timeout),
        "sensitive": False,
        "label": "超时（秒）",
        "description": "单次 AI 调用超时时间。",
        "placeholder": "20",
    },
}


def _mask(key: str, value: Optional[str]) -> Optional[str]:
    """对敏感值做掩码：保留前 4 + 末 4，中间 *"""
    if not value:
        return value
    if len(value) <= 10:
        return "•" * len(value)
    return f"{value[:4]}{'•' * max(4, len(value) - 8)}{value[-4:]}"


def _read_db_value(key: str) -> tuple[Optional[str], Optional[str]]:
    """从 db 读 (value, updated_at_iso)"""
    with Session(engine) as session:
        row = session.get(AppSetting, key)
        if not row:
            return None, None
        return row.value, row.updated_at.isoformat() if row.updated_at else None


def get_setting(key: str) -> tuple[Optional[str], str, bool]:
    """返回 (value_for_use, source, masked)
    - value_for_use: 解码后用于实际调用（始终明文）
    - source: 'db' | 'default'
    - masked: 是否做了脱敏
    """
    definition = SETTING_DEFS.get(key)
    if not definition:
        return None, "default", False

    db_val, _ = _read_db_value(key)
    if db_val is not None and db_val != "":
        return db_val, "db", bool(definition.get("sensitive"))

    default_val = definition.get("default") or ""
    return default_val, "default", bool(definition.get("sensitive"))


def set_setting(key: str, value: Optional[str]) -> None:
    """写入 db。value=None / 空字符串 表示删除（回退默认）"""
    with Session(engine) as session:
        row = session.get(AppSetting, key)
        if value is None or value == "":
            if row:
                session.delete(row)
                logger.info("settings: 已清空 %s（回退默认）", key)
        else:
            if not row:
                row = AppSetting(key=key, value=value)
                session.add(row)
            else:
                row.value = value
            logger.info("settings: 已写入 %s", key)
        session.commit()


def get_all_settings_for_api() -> list[dict]:
    """构造前端需要的展示数据：含 label/description/source/masked"""
    out = []
    for key, definition in SETTING_DEFS.items():
        value, source, sensitive = get_setting(key)
        # 前端拿到的是脱敏值
        api_value = _mask(key, value) if sensitive else value
        _, updated_at = _read_db_value(key)
        out.append({
            "key": key,
            "value": api_value,
            "masked": bool(sensitive),
            "source": source,
            "updated_at": updated_at,
            "label": definition["label"],
            "description": definition["description"],
            "placeholder": definition["placeholder"],
        })
    return out
