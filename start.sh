#!/usr/bin/env bash
# 本地一键启动：启后端 + 内置前端
# 数据持久化到 data/app.db；浏览器访问 http://localhost:8080
set -e
cd "$(dirname "$0")"

mkdir -p data

# 前端构建（每次启动都强制同步）：确保后端 serve 的是最新 chunks
echo "[1/3] 构建前端..."
(cd frontend && npm install --silent && npx vite build)
rm -rf backend/app/static
mkdir -p backend/app/static
cp -r frontend/dist/. backend/app/static/

echo "[2/3] 启动后端 (端口 8080)..."
export DATABASE_URL='sqlite:///./data/app.db'
export PYTHONPATH=backend

# 本地开发模式：启用 admin 密码"开发重置"接口（生产容器不要这个 env）
# 设置后，curl -X POST http://localhost:<port>/api/auth/dev-reset-password \
#   -H "X-Dev-Reset: localdev" -H "Content-Type: application/json" \
#   -d '{"password":"新密码至少8位"}'  就能重置 admin 密码
export DEV_RESET_TOKEN="${DEV_RESET_TOKEN:-localdev}"
# 把 dev-reset-password 加到 auth 网关白名单（默认配置只放行 login/setup/initialized）
export AUTH_PUBLIC_PATHS="${AUTH_PUBLIC_PATHS:-/api/health,/api/auth/login,/api/auth/setup,/api/auth/initialized,/api/auth/dev-reset-password,/_internal/}"

# 准备 Python 依赖：项目根目录用 .venv（不污染系统 python）
VENV_DIR="$(pwd)/.venv"
VENV_PY="$VENV_DIR/bin/python"
ACTIVATE="$VENV_DIR/bin/activate"
# 之前可能存在空目录（早期手动 mkdir 过但 venv 没装上），发现残留就清理
if [ -d "$VENV_DIR" ] && [ ! -x "$VENV_PY" ]; then
  echo "[setup] 发现残留 .venv 目录（不可用），清理后重建..."
  rm -rf "$VENV_DIR"
fi
if [ ! -x "$VENV_PY" ]; then
  echo "[setup] 创建虚拟环境 $VENV_DIR ..."
  python3 -m venv "$VENV_DIR" || { echo "[setup] venv 创建失败：尝试 brew install python3 或 xcode-select --install"; exit 1; }
fi
# shellcheck disable=SC1091
source "$ACTIVATE"

# 同步项目声明的依赖（pyproject.toml）
# sentinel：避免每次启动都走 pip 网络（用户的代理/镜像环境差异大，启动时网络报错很难恢复）
DEPS_SENTINEL="$VENV_DIR/.deps_installed"
NEED_INSTALL=0
if [ ! -f "$DEPS_SENTINEL" ]; then
  NEED_INSTALL=1
elif [ "frontend/package.json" -nt "$DEPS_SENTINEL" ] || [ "pyproject.toml" -nt "$DEPS_SENTINEL" ]; then
  NEED_INSTALL=1
elif ! python -c "import fastapi, sqlmodel, httpx, bs4, lxml, apscheduler, jwt, bcrypt" 2>/dev/null; then
  # sentinel 在但 import 失败（venv 被破坏/换 python 版本）→ 重装
  NEED_INSTALL=1
fi

if [ "$NEED_INSTALL" = "0" ]; then
  echo "[setup] 依赖已就绪（sentinel 命中，跳过 pip）"
else
  echo "[setup] 同步依赖（首次或 pyproject 变更后）..."
  # 关键：临时清掉代理环境变量，否则 pip 会走用户 Clash 端口（7890/50906 等）
  # —— 不清掉，sentinel 也救不了首次安装。
  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
  PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.mirrors.ustc.edu.cn/simple}"
  PIP_OPTS=(
    --index-url "${PIP_INDEX_URL}"
    --quiet
    --disable-pip-version-check
  )
  if pip install "${PIP_OPTS[@]}" --upgrade pip 2>&1 | tail -5; then
    :
  else
    echo "[setup][warn] pip self-upgrade 失败（网络问题），继续安装依赖..."
  fi
  if pip install "${PIP_OPTS[@]}" -e . 2>&1 | tail -20; then
    touch "$DEPS_SENTINEL"
    echo "[setup] 依赖安装完成 → $DEPS_SENTINEL"
  else
    echo "[setup][warn] pip install 失败（网络问题居多）。已安装的依赖继续跑；若缺包请检查代理/镜像后重试。"
  fi
fi

# cloakbrowser 单独装（与 DrissionPage resolver 图冲突，必须 --no-deps；详见 Dockerfile）
# CloakBrowser 取代 DrissionPage 成为默认浏览器（commit 替换 browser.py）
CLOAK_SENTINEL="$VENV_DIR/.cloak_installed"
NEED_CLOAK=0
if [ ! -f "$CLOAK_SENTINEL" ]; then
  NEED_CLOAK=1
elif ! python -c "import cloakbrowser" 2>/dev/null; then
  NEED_CLOAK=1
fi
if [ "$NEED_CLOAK" = "1" ]; then
  echo "[setup] 安装 cloakbrowser（--no-deps 绕过 DrissionPage resolver 冲突）..."
  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
  PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.mirrors.ustc.edu.cn/simple}"
  if pip install --index-url "${PIP_INDEX_URL}" --no-deps --quiet --disable-pip-version-check cloakbrowser 2>&1 | tail -10; then
    touch "$CLOAK_SENTINEL"
    echo "[setup] cloakbrowser 安装完成"
  else
    echo "[setup][warn] cloakbrowser 安装失败（CF 拦截将持续失败）：检查代理/网络后重试"
  fi
fi

# 找空闲端口
PORT=8080
for p in 8080 8081 8082 8090 8888; do
  if ! lsof -i :$p > /dev/null 2>&1; then PORT=$p; break; fi
done
if [ "$PORT" != "8080" ]; then
  echo "[warn] 8080 已被占用（lsof -i :8080 看到旧 uvicorn），切到 $PORT"
  echo "[warn] 浏览器强刷 http://localhost:$PORT 才能看到新代码"
fi

python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
# 等 uvicorn 起来再 open 浏览器（最多等 15 秒）
for i in $(seq 1 30); do
    sleep 0.5
    if curl -fsS "http://127.0.0.1:$PORT/api/sites" > /dev/null 2>&1; then
        break
    fi
done
URL="http://localhost:$PORT"
echo ""
echo "================================================================"
echo "  采集管理面板已启动：$URL"
echo "  停止：按 Ctrl+C，或在 Activity Monitor 里结束 python3"
echo "================================================================"
# 尝试打开浏览器（mac）
if command -v open > /dev/null 2>&1; then
    open "$URL" || true
fi
