#!/usr/bin/env bash
# 容器启动入口：
#   1) 写入 CloakBrowser license
#   2) 若 admin 用户尚未初始化密码：用 Python 生成强随机密码并打印到日志
#   3) 确保 JWT secret 持久化（/app/data/.jwt_secret）
#   4) 预下载 CloakBrowser 二进制
#   5) exec CMD
set -e

echo "[entrypoint] CLOAKBROWSER_LICENSE_KEY=${CLOAKBROWSER_LICENSE_KEY:+***set***}"
if [ -n "${CLOAKBROWSER_LICENSE_KEY}" ]; then
    printf '%s' "${CLOAKBROWSER_LICENSE_KEY}" > "${HOME:-/root}/.cloakbrowser/license.key"
    echo "[entrypoint] License 已写入"
fi

# 确保数据目录存在
mkdir -p /app/data /app/data/profile /app/data/certs

# ---- JWT secret 持久化 ----
# 用一次性随机值写入文件，避免每次重启 token 全部失效（这也会让旧 token 全部失效，仅首次）。
SECRET_FILE="/app/data/.jwt_secret"
if [ ! -s "$SECRET_FILE" ]; then
    python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE" || true
    echo "[entrypoint] JWT secret 已生成并写入 $SECRET_FILE"
fi
export JWT_SECRET="$(cat "$SECRET_FILE")"

# ---- admin 首次密码初始化 ----
# 用 Python 单进程直接更新 users 表的 password_hash（bcrypt）。
# 仅当 password_hash 仍是占位 !UNINITIALIZED! 时才覆盖；其余情况保持现有 admin 不动。
python3 - <<'PY' || true
import os, sys
sys.path.insert(0, "/app/backend")
os.environ.setdefault("DATABASE_URL", "sqlite:////app/data/app.db")
try:
    from sqlmodel import Session, select, create_engine
    from app.models import User
    from app.auth import generate_strong_password, hash_password
except Exception as e:
    print(f"[entrypoint] skip password bootstrap: import error {e}")
    sys.exit(0)

engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})
with Session(engine) as s:
    admin = s.exec(select(User).where(User.username == "admin")).first()
    if admin is None:
        # db.init_db 还没跑（lifespan 在 CMD 启动时建），跳过
        print("[entrypoint] admin 用户尚未创建（lifespan init_db 后将自动创建占位）")
        sys.exit(0)
    if not admin.password_hash.startswith("!UNINITIALIZED!"):
        print("[entrypoint] admin 已初始化，保持现有密码")
        sys.exit(0)
    plain = generate_strong_password(14)
    admin.password_hash = hash_password(plain)
    admin.must_change_password = True
    s.add(admin)
    s.commit()
    print("")
    print("================================================================")
    print(" [CrawlerPanel] 首次启动完成，已生成管理员账号")
    print(f"   用户名: admin")
    print(f"   密码 : {plain}")
    print("   ⚠️  该密码只显示一次，请妥善记录。")
    print("   容器挂载 /app/data 持久化后，下次启动密码保持不变。")
    print("================================================================")
    print("")
PY

# 预下载 CloakBrowser 二进制（仅当未存在时）
if [ ! -d "${HOME:-/root}/.cloakbrowser/chromium-"* ] 2>/dev/null; then
    echo "[entrypoint] 预下载 CloakBrowser 二进制..."
    python3 -m cloakbrowser install || echo "[entrypoint] 预下载失败，将在使用时重试"
fi

echo "[entrypoint] 启动应用..."
exec "$@"
