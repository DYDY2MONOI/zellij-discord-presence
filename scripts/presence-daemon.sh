#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PID_FILE="${ZP_DAEMON_PID:-/tmp/zellij-presence.pid}"
LOG_FILE="${ZP_DAEMON_LOG:-/tmp/zellij-presence.log}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/presence-daemon.sh start [--mode local|wsl-discord] [extra args...]
  bash scripts/presence-daemon.sh stop
  bash scripts/presence-daemon.sh status
  bash scripts/presence-daemon.sh logs
  bash scripts/presence-daemon.sh restart [--mode local|wsl-discord] [extra args...]

Notes:
  - PID file: /tmp/zellij-presence.pid
  - Log file: /tmp/zellij-presence.log
  - For WSL + Discord mode, extra args are forwarded to scripts/run-wsl-discord.sh
EOF
}

is_running() {
  if [[ ! -f "${PID_FILE}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${PID_FILE}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

status() {
  if is_running; then
    echo "running (pid=$(cat "${PID_FILE}"))"
  else
    rm -f "${PID_FILE}"
    echo "stopped"
    return 1
  fi
}

stop() {
  if ! is_running; then
    echo "not running"
    rm -f "${PID_FILE}"
    return 0
  fi

  local pid
  pid="$(cat "${PID_FILE}")"
  kill "${pid}" >/dev/null 2>&1 || true

  for _ in $(seq 1 25); do
    if ! kill -0 "${pid}" >/dev/null 2>&1; then
      rm -f "${PID_FILE}"
      echo "stopped"
      return 0
    fi
    sleep 0.2
  done

  kill -9 "${pid}" >/dev/null 2>&1 || true
  rm -f "${PID_FILE}"
  echo "stopped (forced)"
}

start() {
  local mode="wsl-discord"
  local extra_args=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --mode)
        mode="${2:-}"
        shift 2
        ;;
      *)
        extra_args+=("$1")
        shift
        ;;
    esac
  done

  if is_running; then
    echo "already running (pid=$(cat "${PID_FILE}"))"
    return 0
  fi

  local cmd=()
  case "${mode}" in
    local)
      cmd=(bash scripts/run-now.sh --no-dry-run)
      ;;
    wsl-discord)
      cmd=(bash scripts/run-wsl-discord.sh "${extra_args[@]}")
      ;;
    *)
      echo "invalid mode: ${mode} (use local or wsl-discord)" >&2
      exit 1
      ;;
  esac

  mkdir -p "$(dirname "${PID_FILE}")" "$(dirname "${LOG_FILE}")"
  nohup "${cmd[@]}" >"${LOG_FILE}" 2>&1 &
  local pid=$!
  echo "${pid}" >"${PID_FILE}"

  sleep 0.7
  if ! kill -0 "${pid}" >/dev/null 2>&1; then
    echo "failed to start. last logs:" >&2
    tail -n 40 "${LOG_FILE}" >&2 || true
    rm -f "${PID_FILE}"
    exit 1
  fi

  echo "started (pid=${pid})"
  echo "log: ${LOG_FILE}"
}

logs() {
  touch "${LOG_FILE}"
  tail -f "${LOG_FILE}"
}

main() {
  local action="${1:-}"
  if [[ -z "${action}" ]]; then
    usage
    exit 1
  fi
  shift || true

  case "${action}" in
    start)
      start "$@"
      ;;
    stop)
      stop
      ;;
    status)
      status
      ;;
    logs)
      logs
      ;;
    restart)
      stop || true
      start "$@"
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      echo "unknown action: ${action}" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
