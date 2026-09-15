#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-start}"
if [[ "$ACTION" != "start" && "$ACTION" != "update" ]]; then
  echo "用法: $0 [start|update]"
  exit 1
fi
ACTION_LABEL="启动"
[[ "$ACTION" == "update" ]] && ACTION_LABEL="更新并启动"

# 海外服务器使用各项目官方源。空的 PLAYWRIGHT_DOWNLOAD_HOST 表示微软官方 CDN。
export DEBIAN_MIRROR="http://deb.debian.org/debian"
export DEBIAN_SECURITY_MIRROR="http://deb.debian.org/debian-security"
export PYPI_INDEX_URL="https://pypi.org/simple"
export NPM_REGISTRY="https://registry.npmjs.org"
export PLAYWRIGHT_DOWNLOAD_HOST=""
export PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT="120000"

echo "使用海外官方源${ACTION_LABEL}抖无忧..."
exec "$DEPLOY_DIR/manage.sh" "$ACTION"
