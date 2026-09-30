"""镜像版本元数据。

构建时由 Dockerfile 通过环境变量注入：
  APP_VERSION  - 版本号（v0.1.0 或 0.1.0）
  GIT_SHA      - 完整 git commit sha（40 位）
  BUILT_AT     - 构建时间 ISO8601（UTC）

未注入时全部回退到 "dev" / "unknown"。
"""
from __future__ import annotations

import os

APP_VERSION: str = os.environ.get("APP_VERSION", "dev")
GIT_SHA: str = os.environ.get("GIT_SHA", "unknown")
BUILT_AT: str = os.environ.get("BUILT_AT", "unknown")
