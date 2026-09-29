#!/usr/bin/env bash
# diagnose.sh - 诊断 crawler-panel 是否运行最新镜像
# 用法：bash diagnose.sh

set -e

echo "=========================================="
echo " 1. 本地镜像列表"
echo "=========================================="
docker images ghcr.io/adminmtan/ladycollect --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedAt}}\t{{.Digest}}"
echo ""

echo "=========================================="
echo " 2. .env 内容（IMAGE_TAG 覆盖检查）"
echo "=========================================="
if [ -f .env ]; then
    grep -E "^(IMAGE|IMAGE_TAG)=" .env || echo "(no IMAGE/IMAGE_TAG in .env)"
else
    echo "(no .env file)"
fi
echo ""

echo "=========================================="
echo " 3. registry 上 latest 的最新 digest"
echo "=========================================="
LATEST=$(docker buildx imagetools inspect ghcr.io/adminmtan/ladycollect:latest 2>&1 | head -10 || echo "(buildx inspect failed)")
echo "$LATEST"
echo ""

echo "=========================================="
echo " 4. 当前运行容器使用的镜像"
echo "=========================================="
RUNNING=$(docker inspect crawler-panel --format '{{.Image}}' 2>/dev/null || echo "(容器未运行)")
echo "Running Image: $RUNNING"
echo ""

echo "=========================================="
echo " 5. 容器启动时间（如果很早 = 没重建）"
echo "=========================================="
STARTED=$(docker inspect crawler-panel --format '{{.State.StartedAt}}' 2>/dev/null || echo "(无)")
echo "StartedAt: $STARTED"
echo ""

echo "=========================================="
echo " 6. 应用自身 version（确认是哪个版本）"
echo "=========================================="
HEALTH=$(curl -fsS http://localhost:8080/api/health 2>/dev/null || echo "(无响应)")
echo "Health: $HEALTH"
echo ""

echo "=========================================="
echo " 7. 日志最新 5 行"
echo "=========================================="
docker logs --tail=5 crawler-panel 2>&1 || echo "(无日志)"
echo ""

echo "=========================================="
echo " 修复命令（按需复制）"
echo "=========================================="
cat <<'EOF'
# A. 强制重新拉取 + 重建
docker compose pull
docker compose up -d --force-recreate --remove-orphans

# B. 完全清空 image 后重拉（最彻底）
docker compose down --remove-orphans
docker rmi -f ghcr.io/adminmtan/ladycollect:latest || true
docker compose pull
docker compose up -d

# C. 如果怀疑 .env 锁定了老版本
echo "IMAGE_TAG=latest" > .env
docker compose up -d --force-recreate

# D. 如果 GH Actions 没跑 / 失败
# 去 https://github.com/adminmtan/ladycollect/actions 手动 Re-run
EOF
