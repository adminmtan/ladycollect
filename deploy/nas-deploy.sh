#!/usr/bin/env bash
# 在 Mac 上跑这个脚本，把 deploy/ 部署包同步到 NAS
#
# 用法:
#   NAS_HOST=admin@nas.local NAS_DEPLOY_DIR=~/ladycollect ./deploy/nas-deploy.sh push
#   NAS_HOST=admin@nas.local NAS_DEPLOY_DIR=~/ladycollect ./deploy/nas-deploy.sh update
#   NAS_HOST=admin@nas.local ./deploy/nas-deploy.sh status
#
# 子命令:
#   push     - scp 同步 deploy/ 目录到 NAS（不重启）
#   update   - push + 在 NAS 上 docker compose pull + up -d
#   status   - ssh 上 NAS 看容器状态 + 当前镜像 digest
#   logs     - ssh 上 NAS 看 ladycollect 最近 100 行日志

set -euo pipefail

NAS_HOST="${NAS_HOST:?NAS_HOST required, e.g. admin@192.168.1.10 or admin@nas.local}"
NAS_DEPLOY_DIR="${NAS_DEPLOY_DIR:-~/ladycollect}"
REMOTE_DIR="${NAS_HOST}:${NAS_DEPLOY_DIR}"

SUBCMD="${1:-push}"

case "$SUBCMD" in
  push)
    echo "==> Syncing deploy/ to ${REMOTE_DIR}"
    ssh "${NAS_HOST}" "mkdir -p ${NAS_DEPLOY_DIR}"
    rsync -avz --delete \
      --exclude='.env' \
      --exclude='data/' \
      ./deploy/ "${REMOTE_DIR}/"
    echo "==> Done. Next: SSH to NAS and run:"
    echo "    cd ${NAS_DEPLOY_DIR} && cp .env.example .env \\"
    echo "      && nano .env   # 填 JWT_SECRET 和 ADMIN_PASSWORD"
    echo "      && docker compose pull && docker compose up -d"
    ;;

  update)
    echo "==> Syncing deploy/ to ${REMOTE_DIR}"
    ssh "${NAS_HOST}" "mkdir -p ${NAS_DEPLOY_DIR}"
    rsync -avz --delete \
      --exclude='.env' \
      --exclude='data/' \
      ./deploy/ "${REMOTE_DIR}/"

    echo "==> Pulling new image on NAS"
    ssh "${NAS_HOST}" "cd ${NAS_DEPLOY_DIR} && docker compose pull app"

    echo "==> Restarting container"
    ssh "${NAS_HOST}" "cd ${NAS_DEPLOY_DIR} && docker compose up -d"

    echo "==> Health check"
    sleep 8
    ssh "${NAS_HOST}" "cd ${NAS_DEPLOY_DIR} && docker compose ps && echo '---' && docker compose logs --tail=30 app"
    ;;

  status)
    echo "==> Container status on ${NAS_HOST}"
    ssh "${NAS_HOST}" "cd ${NAS_DEPLOY_DIR} && \
      echo '=== Containers ===' && \
      docker compose ps && \
      echo && \
      echo '=== app image digest ===' && \
      docker inspect ghcr.io/adminmtan/ladycollect:latest --format '{{index .RepoDigests 0}}' 2>&1 || true && \
      echo && \
      echo '=== Disk usage of data/ ===' && \
      du -sh data/ 2>/dev/null || true"
    ;;

  logs)
    echo "==> ladycollect logs on ${NAS_HOST}"
    ssh "${NAS_HOST}" "cd ${NAS_DEPLOY_DIR} && docker compose logs --tail=100 -f app"
    ;;

  *)
    echo "Unknown subcommand: $SUBCMD" >&2
    echo "Usage: $0 {push|update|status|logs}" >&2
    exit 2
    ;;
esac
