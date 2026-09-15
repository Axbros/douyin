#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$DEPLOY_DIR/.env"
if [[ ! -f "$CONFIG_FILE" ]]; then
  CONFIG_FILE="$DEPLOY_DIR/.env.example"
fi

config_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$CONFIG_FILE" | tail -1
}

check_download() {
  local name="$1"
  local url="$2"
  echo "[检查] $name: $url"
  curl -fsSL --retry 2 --connect-timeout 10 --max-time 30 -o /dev/null "$url"
  echo "[正常] $name"
}

debian_mirror="$(config_value DEBIAN_MIRROR)"
pypi_index="$(config_value PYPI_INDEX_URL)"
npm_registry="$(config_value NPM_REGISTRY)"
playwright_host="$(config_value PLAYWRIGHT_DOWNLOAD_HOST)"

check_download "Debian" "${debian_mirror%/}/dists/bookworm/Release"
check_download "PyPI" "${pypi_index%/}/playwright/"
check_download "npm" "${npm_registry%/}/vue"

if [[ -n "$playwright_host" ]]; then
  echo "[检查] Playwright CDN: $playwright_host"
  status="$(curl -sSL --retry 2 --connect-timeout 10 --max-time 30 -o /dev/null -w '%{http_code}' "$playwright_host")"
  if [[ ! "$status" =~ ^[234] ]]; then
    echo "[失败] Playwright CDN 返回 HTTP $status"
    exit 1
  fi
  echo "[正常] Playwright CDN 可访问（HTTP $status）"
fi

echo "[检查] Docker 服务和 Docker Hub 拉取"
docker info >/dev/null
docker pull hello-world >/dev/null
echo "[正常] Docker 镜像拉取成功"

echo "国内镜像检查全部完成。"
