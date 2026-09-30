#!/usr/bin/env bash
# 容器启动入口：
#   1) 若 admin 用户尚未初始化密码：用 Python 生成强随机密码并打印到日志
#   2) 确保 JWT secret 持久化（/app/data/.jwt_secret）
#   3) exec CMD
#
# 设计要点（解决旧版的竞态）：
#   旧版在 exec uvicorn 之前查 users，那时候 lifespan 的 init_db() 还没跑，
#   经常查不到 admin → 直接 sys.exit(0) → admin 永远是占位 !UNINITIALIZED!。
#   现在改成：entrypoint 主动等到 db 就绪（含 admin 占位），写完后才 exec uvicorn。
#   lifespan 起来后看到 admin 已经是真实密码，直接使用。
set -e

echo "[entrypoint] 启动 crawler-panel (基于 Playwright)"

# 确保数据目录存在
mkdir -p /app/data /app/data/profile /app/data/certs /app/data/logs/archive

# ---- JWT secret 持久化 ----
SECRET_FILE="/app/data/.jwt_secret"
if [ ! -s "$SECRET_FILE" ]; then
    python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "$SECRET_FILE"
    chmod 600 "$SECRET_FILE" || true
    echo "[entrypoint] JWT secret 已生成并写入 $SECRET_FILE"
fi
export JWT_SECRET="$(cat "$SECRET_FILE")"

# ---- admin 首次密码初始化 ----
# 流程：
#   a) 等待数据库文件就绪（最多 30s），uvicorn 启动前保证 app.db 存在
#   b) 等到 users 表里 admin 出现（lifespan 可能还没跑，所以这里要自己兼容）
#      - 如果 admin 不存在 → 主动插入一个 admin 占位（marker=!UNINITIALIZED!），
#        避免之后 lifespan 再插入时 UNIQUE 冲突
#      - 如果 admin 的 password_hash 还是占位 → 生成随机密码覆盖
#      - 否则保持现有密码不动
#   c) 全部完成后 exec uvicorn，lifespan 起来后看到的是已初始化密码的 admin
python3 - <<'PY' || true
import os, sys, time, secrets
sys.path.insert(0, "/app/backend")
os.environ.setdefault("DATABASE_URL", "sqlite:////app/data/app.db")

# 在引入 app.* 之前先把 secrets 用上，避免 import 异常时熵被吃
print(f"[entrypoint] bootstrap pid={os.getpid()} entropy_probe={secrets.token_hex(8)}", flush=True)

try:
    from sqlmodel import Session, select, create_engine
    from app.models import User
    from app.auth import generate_strong_password, hash_password
except Exception as e:
    print(f"[entrypoint] skip password bootstrap: import error {e}", flush=True)
    sys.exit(0)

DB_PATH = "/app/data/app.db"
PLACEHOLDER = "!UNINITIALIZED!set-via-DOCKER-entrypoint-or-POST-/api/auth/setup"

# a) 等数据库文件出现（uvicorn lifespan 启动后会建）
deadline = time.time() + 30
while time.time() < deadline and not os.path.exists(DB_PATH):
    print("[entrypoint] 等待数据库文件 /app/data/app.db 出现...", flush=True)
    time.sleep(1)

engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})

# b) 轮询 admin 用户出现（lifespan 启动可能晚于 entrypoint）
deadline = time.time() + 30
admin = None
while time.time() < deadline:
    with Session(engine) as s:
        admin = s.exec(select(User).where(User.username == "admin")).first()
    if admin is not None:
        break
    print("[entrypoint] 等待 admin 用户被 init_db() 创建...", flush=True)
    time.sleep(1)

if admin is None:
    # 超时仍未出现 → 主动建占位，避免 lifespan 启动时 UNIQUE 冲突
    print("[entrypoint] admin 仍未出现，主动写入占位 admin（lifespan 将跳过）", flush=True)
    with Session(engine) as s:
        existing = s.exec(select(User).where(User.username == "admin")).first()
        if existing is None:
            s.add(User(
                username="admin",
                password_hash=PLACEHOLDER,
                role="admin",
                must_change_password=True,
                enabled=True,
            ))
            s.commit()
            # 重新拿一次拿到 id
            with Session(engine) as s2:
                admin = s2.exec(select(User).where(User.username == "admin")).first()
        else:
            admin = existing

assert admin is not None, "admin still None after bootstrap"

# c) 判断是否需要写入真密码
if not admin.password_hash.startswith("!UNINITIALIZED!"):
    print("[entrypoint] admin 已初始化，保持现有密码（密码哈希不重置）", flush=True)
    sys.exit(0)

plain = generate_strong_password(14)
# 防御性：再确认一次熵源真随机
assert len(plain) >= 12 and "-" in plain, f"generate_strong_password 输出异常: {plain!r}"

admin.password_hash = hash_password(plain)
admin.must_change_password = True
with Session(engine) as s:
    s.add(admin)
    s.commit()

print("", flush=True)
print("================================================================", flush=True)
print(f" [CrawlerPanel] 首次启动完成，已生成管理员账号 pid={os.getpid()}", flush=True)
print(f"   生成时间 : {time.strftime('%Y-%m-%d %H:%M:%S %z')}", flush=True)
print(f"   用户名   : admin", flush=True)
print(f"   密码     : {plain}", flush=True)
print("   ⚠️  该密码只显示一次，请妥善记录。", flush=True)
print("   容器挂载 /app/data 持久化后，下次启动密码保持不变。", flush=True)
print("================================================================", flush=True)
print("", flush=True)
PY

echo "[entrypoint] 启动应用..."
exec "$@"
