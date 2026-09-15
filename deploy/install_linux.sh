#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "请使用 sudo 执行此脚本"
  exit 1
fi

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="/opt/douyin"
APP_USER="douyin"

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "未找到 Node.js/npm。请先安装 Node.js 20.19+ 或 22.12+，再重新执行。"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip nginx xvfb xauth rsync curl logrotate fonts-noto-cjk fonts-liberation

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /home/douyin --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_DIR"
if [[ "$SOURCE_DIR" != "$APP_DIR" ]]; then
  rsync -a \
    --exclude '.git/' \
    --exclude '.runtime/' \
    --exclude 'backend/.venv/' \
    --exclude 'frontend/node_modules/' \
    --exclude 'frontend/dist/' \
    "$SOURCE_DIR/" "$APP_DIR/"
fi

if [[ ! -f "$APP_DIR/backend/.env" ]]; then
  echo "缺少 $APP_DIR/backend/.env。请根据 backend/.env.example 创建后重新执行。"
  exit 1
fi
chmod 600 "$APP_DIR/backend/.env"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

if [[ ! -x "$APP_DIR/backend/.venv/bin/python" ]]; then
  runuser -u "$APP_USER" -- python3 -m venv "$APP_DIR/backend/.venv"
fi
runuser -u "$APP_USER" -- "$APP_DIR/backend/.venv/bin/python" -m pip install --upgrade pip
runuser -u "$APP_USER" -- "$APP_DIR/backend/.venv/bin/python" -m pip install -r "$APP_DIR/backend/requirements.txt"

# Playwright 官方依赖安装器需要 root；Chromium 本体安装到业务用户缓存。
"$APP_DIR/backend/.venv/bin/python" -m playwright install-deps chromium
runuser -u "$APP_USER" -- "$APP_DIR/backend/.venv/bin/python" -m playwright install chromium

runuser -u "$APP_USER" -- npm --prefix "$APP_DIR/frontend" ci
runuser -u "$APP_USER" -- npm --prefix "$APP_DIR/frontend" run build

install -m 0644 "$APP_DIR/deploy/systemd/"*.service /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/nginx/douyin.conf" /etc/nginx/sites-available/douyin
ln -sfn /etc/nginx/sites-available/douyin /etc/nginx/sites-enabled/douyin
rm -f /etc/nginx/sites-enabled/default
install -m 0644 "$APP_DIR/deploy/logrotate/douyin" /etc/logrotate.d/douyin

mkdir -p /var/log/douyin
chown "$APP_USER:$APP_USER" /var/log/douyin

systemctl daemon-reload
nginx -t
systemctl enable --now nginx douyin-api.service douyin-login-worker.service douyin-browser-worker.service

TASK_WORKER_PROCESSES="$(sed -n 's/^TASK_WORKER_PROCESSES=//p' "$APP_DIR/backend/.env" | tail -1 | tr -d '[:space:]')"
if [[ ! "$TASK_WORKER_PROCESSES" =~ ^[1-9][0-9]*$ ]]; then
  TASK_WORKER_PROCESSES=1
fi
for ((i=1; i<=TASK_WORKER_PROCESSES; i++)); do
  systemctl enable --now "douyin-task-worker@$i.service"
done

echo "部署完成。请访问服务器地址，或执行: curl http://127.0.0.1/readyz"
echo "服务状态: systemctl status douyin-api douyin-login-worker douyin-browser-worker 'douyin-task-worker@*'"
