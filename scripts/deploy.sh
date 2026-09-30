#!/usr/bin/env bash
# deploy.sh - 一键部署指定 commit 镜像
# 用法：
#   bash deploy.sh                    # 拉最新 main-<HEAD> 镜像并部署
#   bash deploy.sh main-ac03820...    # 拉指定 sha 镜像并部署（精确回滚）
#   IMAGE_TAG=main-ac03820 bash deploy.sh
set -euo pipefail

# 1. 解析目标 tag
TARGET_TAG="${1:-${IMAGE_TAG:-latest}}"

# 2. 如果用户传 latest，自动从 GH 查最新 main-<sha>
if [[ "$TARGET_TAG" == "latest" ]]; then
    echo "[deploy] latest → 查询 GH Actions 最新成功 run 的 sha..."
    if command -v gh >/dev/null 2>&1; then
        SHA=$(gh api repos/adminmtan/ladycollect/commits/main --jq '.sha' 2>/dev/null || echo "")
        if [[ -n "$SHA" ]]; then
            TARGET_TAG="main-${SHA}"
            echo "[deploy] 解析到最新 commit: $TARGET_TAG"
        else
            echo "[deploy] ⚠️ gh CLI 不可用或查询失败，沿用 :latest"
        fi
    else
        echo "[deploy] ⚠️ 未安装 gh CLI，沿用 :latest"
    fi
fi

echo "[deploy] 目标镜像 tag: $TARGET_TAG"
echo "[deploy] ============================ 1. 拉取 ============================"
export IMAGE_TAG="$TARGET_TAG"
docker compose pull

echo "[deploy] ============================ 2. 重建 ============================"
docker compose up -d --force-recreate --remove-orphans

echo "[deploy] ============================ 3. 健康检查 ============================"
sleep 5
for i in 1 2 3 4 5 6; do
    HEALTH=$(curl -fsS http://localhost:8080/api/health 2>/dev/null || echo "")
    if [[ -n "$HEALTH" ]]; then
        echo "[deploy] ✅ 健康检查通过："
        echo "$HEALTH" | python3 -m json.tool
        exit 0
    fi
    echo "[deploy] 等待启动... ($i/6)"
    sleep 3
done

echo "[deploy] ⚠️ 健康检查未通过，请查看 docker logs crawler-panel"
docker logs --tail=30 crawler-panel
exit 1
