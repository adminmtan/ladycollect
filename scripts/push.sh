#!/usr/bin/env bash
# 本机直接推 Docker Hub 镜像（CI 失败 / 偶尔手动推送用）
#
# 用法：
#   IMAGE=youruser/crawler-panel TAG=main-$(git rev-parse --short HEAD) \
#     DOCKERHUB_USERNAME=xxx DOCKERHUB_TOKEN=xxx ./scripts/push.sh
#
# 也可以：
#   ./scripts/push.sh v0.1.0
#   ./scripts/push.sh main
#
# 需要的工具：docker (Desktop / CLI)
set -euo pipefail

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  sed -n '3,18p' "$0"
  exit 0
fi

cd "$(cd "$(dirname "$0")/.." && pwd)"

# 默认值
: "${IMAGE:=mtan/crawler-panel}"
: "${DOCKERHUB_USERNAME:?请先设置 DOCKERHUB_USERNAME}"
: "${DOCKERHUB_TOKEN:?请先设置 DOCKERHUB_TOKEN（Access Token，不要用密码）}"

# 确定 tag
if [ -n "${1:-}" ]; then
  TAG="$1"
elif [ -n "${TAG:-}" ]; then
  TAG="$TAG"
else
  SHORT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  TAG="main-${SHORT}"
fi

echo "==> 登录 Docker Hub"
echo "${DOCKERHUB_TOKEN}" | docker login -u "${DOCKERHUB_USERNAME}" --password-stdin

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
