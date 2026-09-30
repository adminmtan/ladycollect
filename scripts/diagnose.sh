#!/usr/bin/env bash
# diagnose.sh - 诊断 crawler-panel 是否运行最新镜像
# 用法：bash diagnose.sh
#
# 推荐流程：
#   1) bash diagnose.sh       → 看是不是在跑老版本
#   2) IMAGE_TAG=main-<sha> docker compose pull && docker compose up -d --force-recreate

set -e

echo "=========================================="
echo " 1. 本地镜像列表（按时间倒序）"
echo "=========================================="
docker images ghcr.io/adminmtan/ladycollect --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedAt}}"
echo ""

echo "=========================================="
echo " 2. 当前 .env 是否有 IMAGE_TAG 覆盖"
echo "=========================================="
if [ -f .env ]; then
    grep -E "^(IMAGE|IMAGE_TAG)=" .env || echo "(no IMAGE/IMAGE_TAG in .env)"
else
    echo "(no .env file)"
fi
echo ""

echo "=========================================="
echo " 3. registry 上 latest tag 指向哪个 digest"
echo "=========================================="
docker buildx imagetools inspect ghcr.io/adminmtan/ladycollect:latest 2>&1 | head -15 || echo "(buildx inspect failed)"
echo ""

echo "=========================================="
echo " 4. 当前容器实际用的镜像（确认不是老 digest）"
echo "=========================================="
RUNNING=$(docker inspect crawler-panel --format '{{.Image}}' 2>/dev/null || echo "(容器未运行)")
echo "Container Image: $RUNNING"
STARTED=$(docker inspect crawler-panel --format '{{.State.StartedAt}}' 2>/dev/null || echo "(无)")
echo "Container StartedAt: $STARTED"
echo ""

echo "=========================================="
echo " 5. 应用 /api/health（暴露的版本元数据）"
echo "=========================================="
HEALTH=$(curl -fsS http://localhost:8080/api/health 2>/dev/null || echo "(无响应)")
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
echo ""

echo "=========================================="
echo " 6. 最近 5 行日志"
echo "=========================================="
docker logs --tail=5 crawler-panel 2>&1 || echo "(无日志)"
echo ""

echo "=========================================="
echo " 修复命令（按需复制）"
echo "=========================================="
cat <<'EOF'
# A. 最稳的方式 —— 按 commit SHA 精确拉取（永不歧义）
#    1) 查 GitHub Actions 最近成功的 commit sha
#    2) IMAGE_TAG=main-<40位sha> docker compose pull && docker compose up -d --force-recreate

# B. 强制按 latest 拉取（清本地缓存）
docker compose pull
docker compose up -d --force-recreate --remove-orphans

# C. 完全清空 image 后重拉（最彻底）
docker compose down --remove-orphans
docker rmi -f ghcr.io/adminmtan/ladycollect:latest || true
docker compose pull
docker compose up -d
EOF
