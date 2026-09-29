"""统一日志配置：stderr + 文件双输出，按类别分文件，自动压缩。

所有日志同时出现在：
  1. stderr（→ docker logs 可见）
  2. /app/data/logs/<category>.log（容器外可见，bind mount 持久化）
  3. /app/data/logs/errors.log（WARNING+ 汇总）

保留策略 = 大小触发（默认 20MB）+ 备份数量（默认 5）+ 30 天压缩归档清理。
简化说明：只按 size rollover（最稳定），每隔午夜也强制 rollover 一次。
"""
from __future__ import annotations

import gzip
import logging
import os
import re
import shutil
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# 集中放 /app/data/logs，由 docker-compose 的 bind mount 自动持久化
LOGS_DIR_DEFAULT = Path("/app/data/logs")
ARCHIVE_DIR_NAME = "archive"

# 各分类文件大小上限（字节）
MAX_BYTES_DEFAULT = 20 * 1024 * 1024  # 20MB
BACKUP_COUNT_DEFAULT = 5

# archive 目录中 gzip 文件保留天数
ARCHIVE_KEEP_DAYS_DEFAULT = 30

# 每天强制 rollover 一次的"虚拟天号"（UTC 天数），凌晨过 0 点就会变化
_DAY_FMT = "%Y-%m-%d"


def _today_tag() -> str:
    return time.strftime(_DAY_FMT, time.localtime())


class _SizeRotatingWithDailyForcedCut(RotatingFileHandler):
    """标准 RotatingFileHandler + 每天强制切换一次（即使没满 size）。

    - 超 maxBytes：按 .1 .2 ... 滚动
    - 跨过当地午夜：把当前 baseFilename 移到 archive/<name>.<date>，再 gzip
    """

    def __init__(
        self,
        filename: str,
        mode: str = "a",
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: Optional[str] = None,
        delay: bool = False,
        archive_dir: Optional[Path] = None,
        keep_days: int = 30,
    ):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)
        self._archive_dir = Path(archive_dir) if archive_dir else Path(filename).parent / ARCHIVE_DIR_NAME
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        self._keep_days = keep_days
        self._current_day = _today_tag()

    def _maybe_daily_cut(self) -> None:
        today = _today_tag()
        if today == self._current_day:
            return
        self._current_day = today
        # 强制 rollover：把 baseFilename 当前内容移到 archive/<name>.<date>
        self.acquire()
        try:
            if self.stream:
                self.stream.close()
                self.stream = None  # type: ignore[assignment]
            base = Path(self.baseFilename)
            if base.exists() and base.stat().st_size > 0:
                target = self._archive_dir / f"{base.name}.{today}"
                try:
                    base.rename(target)
                    self._gzip(target)
                except OSError:
                    pass
            # 重新打开空 base 文件
            self._open()
            self._purge_old_archives()
        finally:
            self.release()

    def _gzip(self, src: Path) -> None:
        gz = src.with_suffix(src.suffix + ".gz")
        try:
            with open(src, "rb") as fin, gzip.open(gz, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            src.unlink(missing_ok=True)
        except OSError:
            pass

    def _purge_old_archives(self) -> None:
        if self._keep_days <= 0:
            return
        cutoff = time.time() - self._keep_days * 86400
        base_name = Path(self.baseFilename).name
        for gz in self._archive_dir.glob(f"{base_name}.*.gz"):
            try:
                if gz.stat().st_mtime < cutoff:
                    gz.unlink(missing_ok=True)
            except OSError:
                pass

    def emit(self, record: logging.LogRecord) -> None:
        # 跨天先切一次
        self._maybe_daily_cut()
        super().emit(record)


def _classify(record: logging.LogRecord) -> str:
    name = record.name or ""
    if name.startswith("app.crawler") or name == "crawler":
        return "crawler"
    if name.startswith("app.learning"):
        return "learning"
    return "app"


class _CategoryFilter(logging.Filter):
    def __init__(self, allow: str | None):
        super().__init__()
        self._allow = allow

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        if self._allow is None:
            return True  # errors 汇总不过滤
        # 顶层 uvicorn 永远归 app.log
        name = record.name or ""
        if name.startswith("uvicorn"):
            return self._allow == "app"
        return _classify(record) == self._allow


def _build_handler(
    name: str,
    log_dir: Path,
    level: int,
    fmt: logging.Formatter,
    max_bytes: int,
    backup_count: int,
    keep_days: int,
) -> logging.Handler:
    base = log_dir / f"{name}.log"
    handler = _SizeRotatingWithDailyForcedCut(
        filename=str(base),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        archive_dir=log_dir / ARCHIVE_DIR_NAME,
        keep_days=keep_days,
    )
    handler.setLevel(level)
    handler.setFormatter(fmt)
    handler.addFilter(_CategoryFilter(name if name != "errors" else None))
    return handler


def setup_logging(
    logs_dir: Optional[Path] = None,
    max_bytes: int = MAX_BYTES_DEFAULT,
    backup_count: int = BACKUP_COUNT_DEFAULT,
    keep_days: int = ARCHIVE_KEEP_DAYS_DEFAULT,
    level: str = "INFO",
) -> Path:
    """初始化 root logger：stderr + app/crawler/learning/errors 四个文件。"""
    logs_dir = Path(logs_dir) if logs_dir else LOGS_DIR_DEFAULT
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / ARCHIVE_DIR_NAME).mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # 清理掉 basicConfig 已经挂的 handler（避免重复）
    for h in list(root.handlers):
        root.removeHandler(h)

    # 1) stderr → docker logs
    stderr_h = logging.StreamHandler()
    stderr_h.setFormatter(fmt)
    stderr_h.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(stderr_h)

    # 2) 三个分类文件
    for name in ("app", "crawler", "learning"):
        h = _build_handler(
            name=name,
            log_dir=logs_dir,
            level=logging.DEBUG,
            fmt=fmt,
            max_bytes=max_bytes,
            backup_count=backup_count,
            keep_days=keep_days,
        )
        root.addHandler(h)

    # 3) errors 汇总（不过滤，所有 WARNING+）
    err_h = _build_handler(
        name="errors",
        log_dir=logs_dir,
        level=logging.WARNING,
        fmt=fmt,
        max_bytes=max_bytes,
        backup_count=backup_count,
        keep_days=keep_days,
    )
    root.addHandler(err_h)

    # uvicorn 自身 logger 接到我们的 root
    for uv in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(uv)
        lg.handlers = []
        lg.propagate = True
        lg.setLevel(logging.INFO)

    # 安静一些的库
    logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    root.info(
        "[logging] 日志系统已初始化: dir=%s max_bytes=%d backup=%d keep_days=%d",
        logs_dir, max_bytes, backup_count, keep_days,
    )
    return logs_dir