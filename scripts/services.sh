#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"
PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
UVICORN_BIN="$ROOT_DIR/backend/.venv/bin/uvicorn"

mkdir -p "$PID_DIR" "$LOG_DIR"

worker_count() {
  local value
  value="$(sed -n 's/^TASK_WORKER_PROCESSES=//p' "$ROOT_DIR/backend/.env" 2>/dev/null | tail -1 | tr -d '[:space:]')"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    value=1
  fi
  printf '%s' "$value"
}

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

start_service() {
  local name="$1"
  shift
  local pid_file="$PID_DIR/$name.pid"
  if is_running "$pid_file"; then
    echo "[运行中] ${name} (PID $(cat "$pid_file"))"
    return
  fi
  rm -f "$pid_file"
  nohup "$@" >>"$LOG_DIR/$name.log" 2>&1 &
  local pid=$!
  echo "$pid" >"$pid_file"
  sleep 0.4
  if kill -0 "$pid" 2>/dev/null; then
    echo "[已启动] ${name} (PID $pid)"
  else
    echo "[启动失败] ${name}，请查看 $LOG_DIR/${name}.log"
    rm -f "$pid_file"
  fi
}

stop_service() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"
  if ! is_running "$pid_file"; then
    rm -f "$pid_file"
    echo "[未运行] ${name}"
    return
  fi
  local pid
  pid="$(cat "$pid_file")"
  kill "$pid" 2>/dev/null || true
  for _ in {1..20}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
  echo "[已停止] ${name}"
}

start_all() {
  if [[ ! -x "$PYTHON_BIN" || ! -x "$UVICORN_BIN" ]]; then
    echo "未找到 backend/.venv，请先创建虚拟环境并安装 backend/requirements.txt"
    exit 1
  fi
  if [[ ! -f "$ROOT_DIR/backend/.env" ]]; then
    echo "未找到 backend/.env"
    exit 1
  fi
  start_service api env PYTHONPATH="$ROOT_DIR/backend:$ROOT_DIR" "$UVICORN_BIN" app.main:app --app-dir "$ROOT_DIR/backend" --host 127.0.0.1 --port 8000
  start_service login-worker env PYTHONPATH="$ROOT_DIR/backend:$ROOT_DIR" WORKER_INSTANCE_ID=login "$PYTHON_BIN" "$ROOT_DIR/backend/workers/login_worker.py"
  start_service browser-worker env PYTHONPATH="$ROOT_DIR/backend:$ROOT_DIR" WORKER_INSTANCE_ID=browser "$PYTHON_BIN" "$ROOT_DIR/backend/workers/account_browser_worker.py"
  local count
  count="$(worker_count)"
  for ((i=1; i<=count; i++)); do
    start_service "task-worker-$i" env PYTHONPATH="$ROOT_DIR/backend:$ROOT_DIR" WORKER_INSTANCE_ID="$i" "$PYTHON_BIN" "$ROOT_DIR/backend/workers/task_worker.py"
  done
  if command -v npm >/dev/null 2>&1; then
    start_service frontend npm --prefix "$ROOT_DIR/frontend" run dev -- --host 0.0.0.0
  else
    echo "[跳过] frontend：未找到 npm"
  fi
}

stop_all() {
  for pid_file in "$PID_DIR"/*.pid; do
    [[ -e "$pid_file" ]] || continue
    stop_service "$(basename "$pid_file" .pid)"
  done
}

show_status() {
  local found=0
  for pid_file in "$PID_DIR"/*.pid; do
    [[ -e "$pid_file" ]] || continue
    found=1
    local name
    name="$(basename "$pid_file" .pid)"
    if is_running "$pid_file"; then
      echo "[运行中] ${name} (PID $(cat "$pid_file"))"
    else
      echo "[已退出] ${name}"
    fi
  done
  [[ "$found" -eq 1 ]] || echo "当前没有由此脚本管理的服务"
}

case "${1:-}" in
  start) start_all ;;
  stop) stop_all ;;
  restart) stop_all; start_all ;;
  status) show_status ;;
  *) echo "用法: $0 {start|stop|restart|status}"; exit 1 ;;
esac
