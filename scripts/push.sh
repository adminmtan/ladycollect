#!/usr/bin/env bash
# 本机直接推 GHCR 镜像（CI 失败 / 偶尔手动推送用）
#
# 用法：
#   IMAGE=ghcr.io/adminmtan/ladycollect TAG=main-$(git rev-parse --short HEAD) \
#     GITHUB_TOKEN=ghp_xxx ./scripts/push.sh
#
# 也可以：
#   ./scripts/push.sh v0.1.0
#   ./scripts/push.sh main
#
# 需要的工具：docker (Desktop / CLI)
# 需要的凭证：GITHUB_TOKEN（需要有 packages:write 权限的 PAT）
set -euo pipefail

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '3,18p' "$0"
  exit 0
fi

cd "$(cd "$(dirname "$0")/.." && pwd)"

# 默认值
: "${IMAGE:=ghcr.io/adminmtan/ladycollect}"
: "${GITHUB_USERNAME:=adminmtan}"
: "${GITHUB_TOKEN:?请先设置 GITHUB_TOKEN（需 packages:write 权限的 PAT）}"

# 确定 tag
if [ -n "${1:-}" ]; then
  TAG="$1"
elif [ -n "${TAG:-}" ]; then
  TAG="$TAG"
else
  SHORT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  TAG="main-${SHORT}"
fi

echo "==> 登录 GHCR (ghcr.io)"
echo "${GITHUB_TOKEN}" | docker login ghcr.io -u "${GITHUB_USERNAME}" --password-stdin

echo "==> 构建 ${IMAGE}:${TAG}"
docker build \
  --tag "${IMAGE}:${TAG}" \
  --tag "${IMAGE}:latest" \
  --label "org.opencontainers.image.source=$(git remote get-url origin 2>/dev/null || echo unknown)" \
  .

echo "==> 推送 ${IMAGE}:${TAG}"
docker push "${IMAGE}:${TAG}"
docker push "${IMAGE}:latest"

echo ""
echo "✓ 已推送 ${IMAGE}:${TAG}  和  ${IMAGE}:latest"
echo ""
echo "NAS 上升级："
echo "  cd ~/crawler-panel && docker compose pull && docker compose up -d"
