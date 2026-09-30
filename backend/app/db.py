"""数据库引擎与会话"""
from __future__ import annotations

import logging
import os

from sqlmodel import Session, SQLModel, create_engine, select

from app.config import settings

logger = logging.getLogger(__name__)


def _make_engine():
    """创建 SQLAlchemy 引擎（SQLite 需开启 check_same_thread=False）

    连接池策略：
      - SQLite 用 NullPool（每次新建连接，避免锁竞争 & "QueuePool limit" 错误）
      - 其它数据库走默认 QueuePool，但显式放宽上限
    """
    url = settings.database_url
    connect_args = {}
    engine_kwargs: dict = {"echo": False, "connect_args": connect_args}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        # SQLite 单文件 + WAL 模式下，每个请求用独立连接最稳；
        # 用 NullPool 而不是 StaticPool，避免多线程争抢同一连接
        from sqlalchemy.pool import NullPool
        engine_kwargs["poolclass"] = NullPool
    else:
        # Postgres/MySQL：放宽池子，并启用 recycle
        engine_kwargs["pool_size"] = 20
        engine_kwargs["max_overflow"] = 20
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_recycle"] = 1800
    return create_engine(url, **engine_kwargs)


engine = _make_engine()


def init_db() -> None:
    """首次启动创建所有表，并对存量库做轻量迁移"""
    # 导入所有模型以注册到 metadata
    from app import models  # noqa: F401

    SQLModel.metadata.create_all(engine)

    # 轻量 ALTER：sites 表已有时，补齐新增的过滤词字段
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(sites)").fetchall()}
            statements = []
            if "title_include_keywords" not in cols:
                statements.append(
                    "ALTER TABLE sites ADD COLUMN title_include_keywords JSON DEFAULT '[]'"
                )
            if "title_exclude_keywords" not in cols:
                statements.append(
                    "ALTER TABLE sites ADD COLUMN title_exclude_keywords JSON DEFAULT '[]'"
                )
            if "adapter" not in cols:
                statements.append(
                    "ALTER TABLE sites ADD COLUMN adapter VARCHAR(32) DEFAULT 'onemei'"
                )
            for stmt in statements:
                conn.exec_driver_sql(stmt)
                logger.info("已迁移：%s", stmt)
    except Exception as e:  # pragma: no cover
        logger.warning("sites 表迁移跳过：%s", e)

    # 轻量 ALTER：tasks 表已有时，补齐调度字段
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            tcols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(tasks)").fetchall()}
            tstmts = []
            if "cron" not in tcols:
                tstmts.append("ALTER TABLE tasks ADD COLUMN cron VARCHAR(64) DEFAULT NULL")
            if "schedule_enabled" not in tcols:
                tstmts.append("ALTER TABLE tasks ADD COLUMN schedule_enabled BOOLEAN DEFAULT 0")
            if "name_template" not in tcols:
                tstmts.append("ALTER TABLE tasks ADD COLUMN name_template VARCHAR(120) DEFAULT NULL")
            if "next_run_at" not in tcols:
                tstmts.append("ALTER TABLE tasks ADD COLUMN next_run_at DATETIME DEFAULT NULL")
            if "last_run_at" not in tcols:
                tstmts.append("ALTER TABLE tasks ADD COLUMN last_run_at DATETIME DEFAULT NULL")
            if "list_urls" not in tcols:
                tstmts.append("ALTER TABLE tasks ADD COLUMN list_urls JSON DEFAULT '[]'")
            if "site_ids" not in tcols:
                tstmts.append("ALTER TABLE tasks ADD COLUMN site_ids JSON DEFAULT '[]'")
            for s in tstmts:
                try:
                    conn.exec_driver_sql(s)
                    logger.info("已迁移：%s", s)
                except Exception:
                    pass
            # data migration: existing site_id rows -> site_ids JSON array
            legacy = conn.exec_driver_sql(
                "SELECT id, site_id FROM tasks WHERE site_id IS NOT NULL AND (site_ids IS NULL OR site_ids='[]')"
            ).fetchall()
            for tid, sid in legacy:
                conn.exec_driver_sql(
                    "UPDATE tasks SET site_ids=? WHERE id=?",
                    (str([sid]), tid),
                )
            if legacy:
                logger.info("已迁移 site_id → site_ids，共 %d 条", len(legacy))
            # SQLite 重建 tasks 表：把 site_id 改为 nullable（旧 schema 是 NOT NULL，
            # 新架构用 site_ids，site_id 保留兼容但允许空）
            tinfo = conn.exec_driver_sql("PRAGMA table_info(tasks)").fetchall()
            site_id_col = next((c for c in tinfo if c[1] == 'site_id'), None)
            if site_id_col and site_id_col[3] == 1:  # notnull=1
                logger.info("重建 tasks 表：site_id → nullable")
                # 备份旧表 → 新表 → 拷贝
                cols = [c[1] for c in tinfo if c[1] != 'site_id']
                conn.exec_driver_sql("ALTER TABLE tasks RENAME TO tasks__old")
                # 用 sqlmodel 自动建表
                from app.models import Task as _Task  # noqa: F401
                _Task.__table__.create(conn, checkfirst=True)
                # 拷贝数据
                col_list = ", ".join(cols)
                conn.exec_driver_sql(
                    f"INSERT INTO tasks ({col_list}) SELECT {col_list} FROM tasks__old"
                )
                conn.exec_driver_sql("DROP TABLE tasks__old")
                logger.info("tasks 表重建完成")
            # Sites table: forum_fid + list_urls
            scols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(sites)").fetchall()}
            site_stmts = []
            if "forum_fid" not in scols:
                site_stmts.append("ALTER TABLE sites ADD COLUMN forum_fid VARCHAR(40) DEFAULT NULL")
            if "list_urls" not in scols:
                site_stmts.append("ALTER TABLE sites ADD COLUMN list_urls JSON DEFAULT '[]'")
            for s in site_stmts:
                try:
                    conn.exec_driver_sql(s)
                    logger.info("已迁移：%s", s)
                except Exception:
                    pass
    except Exception as e:  # pragma: no cover
        logger.warning("tasks 表迁移跳过：%s", e)

    # 轻量 ALTER：jobs 表已有时，补齐 display_name
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            jcols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(jobs)").fetchall()}
            if "display_name" not in jcols:
                conn.exec_driver_sql("ALTER TABLE jobs ADD COLUMN display_name VARCHAR(160) DEFAULT NULL")
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_jobs_display_name ON jobs(display_name)")
                logger.info("已迁移：jobs.display_name")
    except Exception as e:  # pragma: no cover
        logger.warning("jobs 表迁移跳过：%s", e)

    # 智能过滤学习：filter_rules / filter_keywords / user_feedback 三张表
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS filter_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(160) NOT NULL,
                    scope VARCHAR(16) NOT NULL DEFAULT 'site',
                    site_id INTEGER,
                    rule_type VARCHAR(16) NOT NULL DEFAULT 'exclude',
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    note TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE
                )
                """
            )
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_filter_rules_scope ON filter_rules(scope)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_filter_rules_rule_type ON filter_rules(rule_type)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_filter_rules_site_id ON filter_rules(site_id)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_filter_rules_name ON filter_rules(name)")
            logger.info("已确保：filter_rules 表存在")

            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS filter_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id INTEGER NOT NULL,
                    keyword VARCHAR(160) NOT NULL,
                    source VARCHAR(24) NOT NULL DEFAULT 'manual',
                    weight REAL DEFAULT 1.0,
                    hit_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (rule_id) REFERENCES filter_rules(id) ON DELETE CASCADE
                )
                """
            )
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_filter_keywords_rule_id ON filter_keywords(rule_id)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_filter_keywords_keyword ON filter_keywords(keyword)")
            logger.info("已确保：filter_keywords 表存在")

            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS user_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER,
                    site_id INTEGER,
                    title VARCHAR(500) NOT NULL,
                    action VARCHAR(16) NOT NULL,
                    keywords_extracted JSON DEFAULT '[]',
                    rule_id INTEGER,
                    rule_type VARCHAR(16),
                    note TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE SET NULL,
                    FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE SET NULL,
                    FOREIGN KEY (rule_id) REFERENCES filter_rules(id) ON DELETE SET NULL
                )
                """
            )
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_user_feedback_post_id ON user_feedback(post_id)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_user_feedback_site_id ON user_feedback(site_id)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_user_feedback_action ON user_feedback(action)")
            logger.info("已确保：user_feedback 表存在")
    except Exception as e:  # pragma: no cover
        logger.warning("过滤学习表迁移跳过：%s", e)

    # 应用级运行时配置（key/value 持久化；覆盖 .env 默认）
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key VARCHAR(64) PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_app_settings_updated_at ON app_settings(updated_at)"
            )
            logger.info("已确保：app_settings 表存在")
    except Exception as e:  # pragma: no cover
        logger.warning("app_settings 表迁移跳过：%s", e)

    # 用户认证表
    try:
        from sqlmodel import Session as _Session  # noqa: F401
        from app.models import User

        with engine.begin() as conn:
            conn.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(64) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(16) NOT NULL DEFAULT 'admin',
                    must_change_password BOOLEAN NOT NULL DEFAULT 1,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_users_username ON users(username)"
            )
            logger.info("已确保：users 表存在")

        # 确保有 admin 用户（首条记录的 row）。如果 entrypoint 已写入正式密码，这里只在没用户时建占位。
        with Session(engine) as s:  # noqa: F821  (sqlmodel.Session)
            from sqlmodel import select
            existing = s.exec(select(User).where(User.username == "admin")).first()
            if existing is None:
                # 占位密码将由 docker-entrypoint.sh 在容器首次启动时覆盖；
                # 本地没有 entrypoint 的情况下，给一个明显的"未初始化"提示。
                marker = "!UNINITIALIZED!set-via-DOCKER-entrypoint-or-POST-/api/auth/setup"
                s.add(User(
                    username="admin",
                    password_hash=marker,
                    role="admin",
                    must_change_password=True,
                    enabled=True,
                ))
                s.commit()
                existing = s.exec(select(User).where(User.username == "admin")).first()
                logger.warning(
                    "已创建占位 admin 用户（password_hash=!UNINITIALIZED!）。"
                    "Docker 模式：entrypoint.sh 会生成强随机密码并打到日志。"
                    "本地开发模式：先 POST /api/auth/setup 初始化密码。"
                )

            # 本地（非 docker）直接生成本地 dev 密码，避免用户必须先 curl /api/auth/setup 才能登录。
            # 触发条件：admin 用户的 password_hash 仍是占位（首次启动 / 用户从未初始化过）。
            # 容器内 /app 存在时跳过这段，由 docker-entrypoint.sh 负责。
            import os as _os
            if not _os.path.isdir("/app") and existing is not None and existing.password_hash.startswith("!UNINITIALIZED!"):
                try:
                    from app.api.auth import generate_strong_password
                    from app.auth import hash_password as _hp
                    plain = generate_strong_password(14)
                    existing.password_hash = _hp(plain)
                    existing.must_change_password = True
                    s.add(existing)
                    s.commit()
                    # 单独用 root logger 打一醒目的 banner，便于用户从 start.sh 的 stderr 中复制
                    logging.getLogger().info(
                        "\n================================================================\n"
                        "  [本地 dev 模式] 已生成 admin 初始密码：%s\n"
                        "  访问 http://localhost:%s/login，用 admin + 上面密码登录。"
                        "  （生产容器由 docker-entrypoint.sh 处理，不会走这段）\n"
                        "================================================================",
                        plain,
                        _os.environ.get("APP_PORT", "8080"),
                    )
                except Exception as _e:  # pragma: no cover
                    logger.warning("本地初始化 admin 密码失败（可忽略，仍可走 /api/auth/setup）：%s", _e)
    except Exception as e:  # pragma: no cover
        logger.warning("users 表迁移跳过：%s", e)

    # 清理 stale running jobs：进程重启/崩溃后，DB 仍 status='running' 但采集线程已死。
    # 启动时把超过 STALE_JOB_MINUTES 还没结束的 job 标为 cancelled（避免「停止按钮没作用」假象）。
    try:
        from datetime import datetime, timedelta, timezone as _tz
        stale_minutes = int(os.environ.get("STALE_JOB_MINUTES", "30"))
        cutoff = datetime.now(_tz.utc) - timedelta(minutes=stale_minutes)
        with Session(engine) as s:
            stale = s.exec(
                select(Job).where(Job.status == "running", Job.started_at < cutoff)
            ).all()
            for j in stale:
                j.status = "cancelled"
                j.error = j.error or "采集进程已退出（stale cleanup）"
                j.finished_at = datetime.now(_tz.utc)
                s.add(j)
                _append_log_safe(j, "⛔ 采集进程已退出，状态自动标记为 cancelled（stale cleanup）", s)
                s.commit()
                logger.warning("stale job cleanup: job_id=%s 已标 cancelled", j.id)
    except Exception as e:  # pragma: no cover
        logger.warning("stale job cleanup 跳过：%s", e)


def get_session() -> Session:
    """FastAPI 依赖：每次请求一个 Session"""
    return Session(engine)


def _append_log_safe(job, msg: str, session: Session) -> None:
    """不依赖 logger 的轻量日志写入（用于 stale cleanup 这类启动期操作）"""
    try:
        from app.models import JobLog
        session.add(JobLog(job_id=job.id, ts=datetime.now(_tz.utc), msg=msg))
        session.commit()
    except Exception:
        pass
