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

# 找空闲端口
PORT=8080
for p in 8080 8081 8082 8090 8888; do
  if ! lsof -i :$p > /dev/null 2>&1; then PORT=$p; break; fi
done

python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT &
UVICORN_PID=$!
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
# 阻塞直到 uvicorn 退出（无论退出码如何都保持 Terminal 窗口不关）
wait $UVICORN_PID || true
