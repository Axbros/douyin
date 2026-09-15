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

# 这些环境变量优先于 .env 中的同名构建项，只影响依赖下载源，不读取或复制密码。
export DEBIAN_MIRROR="https://mirrors.aliyun.com/debian"
export DEBIAN_SECURITY_MIRROR="https://mirrors.aliyun.com/debian-security"
export PYPI_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
export NPM_REGISTRY="https://registry.npmmirror.com"
export PLAYWRIGHT_DOWNLOAD_HOST="https://cdn.npmmirror.com/binaries/playwright"
export PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT="120000"

echo "使用中国大陆镜像${ACTION_LABEL}抖无忧..."
exec "$DEPLOY_DIR/manage.sh" "$ACTION"
