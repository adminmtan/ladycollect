#!/usr/bin/env bash
# update.sh - 升级到指定 commit 的镜像
#
# 用法：
#   bash scripts/update.sh                # 默认拉取 GitHub Actions 最近成功的 main commit
#   bash scripts/update.sh ac03820        # 指定 commit 前缀
#   bash scripts/update.sh v0.1.0         # 指定 semver tag
#   IMAGE_TAG=main-ac03820... bash scripts/update.sh
#
# 流程：
#   1) 拉目标 tag
#   2) IMAGE_TAG=<target> docker compose up -d --force-recreate
#   3) 等待健康检查通过
#   4) 打印前后版本对比

set -euo pipefail

REPO="ghcr.io/adminmtan/ladycollect"
TARGET="${1:-${IMAGE_TAG:-latest}}"

# 颜色
G="\033[0;32m"; Y="\033[1;33m"; R="\033[0;31m"; N="\033[0m"

# ---------- 1. 拿当前运行版本 ----------
echo -e "${Y}== 当前版本 ==${N}"
BEFORE_SHA=$(docker inspect crawler-panel --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' 2>/dev/null || echo "unknown")
BEFORE_TAG=$(docker inspect crawler-panel --format '{{index .Config.Labels "org.opencontainers.image.title"}}' 2>/dev/null || echo "unknown")
curl -fsS http://localhost:8080/api/health 2>/dev/null | python3 -m json.tool 2>/dev/null | sed 's/^/  /' || echo "  (容器未运行)"
echo ""

# ---------- 2. 解析 target ----------
case "$TARGET" in
    latest)
        TAG="latest"
        ;;
    v*.*.*)
        TAG="$TARGET"
        ;;
    [0-9a-f]*)
        # commit 前缀，补全为 main-<完整 sha>
        SHA_FULL=$(curl -fsSL "https://api.github.com/repos/adminmtan/ladycollect/commits?sha=main&per_page=1" 2>/dev/null \
            | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['sha'])" 2>/dev/null || echo "")
        if [ -z "$SHA_FULL" ]; then
            echo -e "${R}无法从 GitHub API 查 commit，请检查网络或传 v0.1.0 形式${N}"
            exit 1
        fi
        # 如果传的 short prefix 匹配 sha_full 前缀，用 sha_full
        if [[ "$SHA_FULL" == "$TARGET"* ]]; then
            TAG="main-$SHA_FULL"
        else
            # 直接用 short 前缀作为 main-<short>
            TAG="main-$TARGET"
        fi
        ;;
    *)
        echo -e "${R}未知 target: $TARGET${N}"
        echo "用法: $0 [latest|v0.1.0|<commit前7位>|<完整sha>]"
        exit 1
        ;;
esac

echo -e "${Y}== 拉取 $REPO:$TAG ==${N}"
if ! docker pull "$REPO:$TAG"; then
    echo -e "${R}拉取失败，请确认 GH Actions 已发布该 tag${N}"
    exit 1
fi
echo ""

# ---------- 3. 重建容器 ----------
echo -e "${Y}== 重建容器（IMAGE_TAG=$TAG）==${N}"
IMAGE_TAG="$TAG" docker compose up -d --force-recreate --remove-orphans
echo ""

# ---------- 4. 等健康检查 ----------
echo -e "${Y}== 等待健康检查通过 ==${N}"
for i in {1..30}; do
    if curl -fsS http://localhost:8080/api/health > /dev/null 2>&1; then
        echo -e "${G}✓ 健康检查通过${N}"
        break
    fi
    echo "  等待中... ($i/30)"
    sleep 2
done
echo ""

# ---------- 5. 打印新版本 ----------
echo -e "${Y}== 新版本 ==${N}"
curl -fsS http://localhost:8080/api/health | python3 -m json.tool 2>/dev/null | sed 's/^/  /'
echo ""
echo -e "${G}升级完成。${N}"
