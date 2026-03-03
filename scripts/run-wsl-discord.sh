#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONFIG_PATH="${ZP_CONFIG_PATH:-/tmp/zellij-presence-wsl.toml}"
OUTPUT_PATH="${ZP_OUTPUT_PATH:-/tmp/zellij-presence.json}"
SOCKET_PATH="${ZP_DISCORD_SOCKET_PATH:-/tmp/discord-ipc-0}"
CLIENT_ID="${ZP_DISCORD_CLIENT_ID:-}"
NPIPERELAY_PATH="${ZP_NPIPERELAY_PATH:-}"
PIPE_INDEX="${ZP_DISCORD_PIPE_INDEX:-auto}"
DEFAULT_CLIENT_ID="1478178019074904085"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/run-wsl-discord.sh

Options:
  --client-id ID     Discord application client ID (optional override).
  --config PATH      Config output path (default: /tmp/zellij-presence-wsl.toml).
  --socket PATH      Unix socket path for relay (default: /tmp/discord-ipc-0).
  --output PATH      Presence JSON output path (default: /tmp/zellij-presence.json).
  --npiperelay PATH  Path to npiperelay.exe (optional, auto-detected when omitted).
  --pipe-index N     Windows Discord pipe index 0..9, or "auto" (default).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --client-id)
      CLIENT_ID="${2:-}"
      shift 2
      ;;
    --config)
      CONFIG_PATH="${2:-}"
      shift 2
      ;;
    --socket)
      SOCKET_PATH="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT_PATH="${2:-}"
      shift 2
      ;;
    --npiperelay)
      NPIPERELAY_PATH="${2:-}"
      shift 2
      ;;
    --pipe-index)
      PIPE_INDEX="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${CLIENT_ID}" ]]; then
  CLIENT_ID="${DEFAULT_CLIENT_ID}"
fi

if [[ -z "${WSL_DISTRO_NAME:-}" ]]; then
  echo "This script is intended for WSL." >&2
  exit 1
fi

if ! command -v socat >/dev/null 2>&1; then
  echo "socat is required. Install with: sudo apt-get install socat" >&2
  exit 1
fi

detect_npiperelay() {
  local requested="${NPIPERELAY_PATH}"
  if [[ -n "${requested}" ]]; then
    # Accept raw Windows paths (eg. C:\Tools\npiperelay\npiperelay.exe).
    if [[ "${requested}" =~ ^[A-Za-z]:\\ ]] && command -v wslpath >/dev/null 2>&1; then
      requested="$(wslpath "${requested}")"
    fi
    if [[ -f "${requested}" ]]; then
      echo "${requested}"
      return
    fi
  fi
  if command -v npiperelay.exe >/dev/null 2>&1; then
    command -v npiperelay.exe
    return
  fi
  shopt -s nullglob
  local patterns=(
    "/mnt/c/Users/*/scoop/apps/npiperelay/current/npiperelay.exe"
    "/mnt/c/Users/*/AppData/Local/Microsoft/WinGet/Packages/jstarks.npiperelay_Microsoft.Winget.Source_8wekyb3d8bbwe/npiperelay.exe"
  )
  local pattern
  local path
  for pattern in "${patterns[@]}"; do
    for path in ${pattern}; do
      if [[ -f "${path}" ]]; then
        echo "${path}"
        shopt -u nullglob
        return
      fi
    done
  done
  shopt -u nullglob
}

NPIPERELAY_BIN="$(detect_npiperelay || true)"
if [[ -z "${NPIPERELAY_BIN}" ]]; then
  if [[ -n "${NPIPERELAY_PATH}" ]]; then
    echo "Requested --npiperelay path was not found: ${NPIPERELAY_PATH}" >&2
  fi
  cat >&2 <<'EOF'
npiperelay.exe not found.
Install it on Windows and pass its path with:
  --npiperelay /mnt/c/path/to/npiperelay.exe
EOF
  exit 1
fi

echo "==> Using npiperelay: ${NPIPERELAY_BIN}"

echo "==> Writing config to ${CONFIG_PATH}"
cat >"${CONFIG_PATH}" <<EOF
safe_mode = true
poll_interval_seconds = 0.5

[collector]
strategy = "cli"
plugin_state_file = "/tmp/zellij-presence-plugin-state.json"
plugin_max_age_seconds = 2.0

[publish]
file_path = "${OUTPUT_PATH}"
http_enabled = false
http_host = "127.0.0.1"
http_port = 4765

[publish.discord]
enabled = true
client_id = "${CLIENT_ID}"
socket_path = "${SOCKET_PATH}"

[filters]
allow_commands = ["nvim", "vim", "git", "python", "cargo", "make"]
deny_paths = ["~/Documents/secret", "~/.ssh", "~/.gnupg"]
redact_patterns = [
  "(?i)(token|secret|password|passwd|api[_-]?key)\\\\s*[:=]\\\\s*([^\\\\s]+)",
  "\\\\beyJ[A-Za-z0-9_-]{10,}\\\\.[A-Za-z0-9_-]{10,}\\\\.[A-Za-z0-9_-]{10,}\\\\b",
  "\\\\b(?:ghp|gho|ghu|ghs|glpat|xox[baprs]-|sk_(?:live|test))[A-Za-z0-9_-]{8,}\\\\b",
]
EOF

PIPE_NAME="//./pipe/discord-ipc-0"
SOCKET_DIR="$(dirname "${SOCKET_PATH}")"
mkdir -p "${SOCKET_DIR}"
rm -f "${SOCKET_PATH}"

start_relay() {
  local idx="$1"
  local pipe_name="//./pipe/discord-ipc-${idx}"
  rm -f "${SOCKET_PATH}"
  echo "==> Trying Discord IPC relay (${SOCKET_PATH} -> ${pipe_name})"
  socat "UNIX-LISTEN:${SOCKET_PATH},fork,unlink-close,unlink-early" \
    "EXEC:${NPIPERELAY_BIN} -ep -s ${pipe_name},nofork" >/tmp/zp-discord-relay.log 2>&1 &
  RELAY_PID=$!
  sleep 0.3
  if kill -0 "${RELAY_PID}" >/dev/null 2>&1; then
    echo "==> Relay connected on pipe index ${idx}"
    return 0
  fi
  wait "${RELAY_PID}" >/dev/null 2>&1 || true
  return 1
}

RELAY_PID=""
SERVICE_PID=""
if [[ "${PIPE_INDEX}" == "auto" ]]; then
  connected=0
  for idx in 0 1 2 3 4 5 6 7 8 9; do
    if start_relay "${idx}"; then
      connected=1
      break
    fi
  done
  if [[ "${connected}" -ne 1 ]]; then
    echo "Relay could not connect to any discord-ipc pipe (0..9). See /tmp/zp-discord-relay.log" >&2
    echo "Make sure Windows Discord desktop is running." >&2
    exit 1
  fi
else
  if [[ ! "${PIPE_INDEX}" =~ ^[0-9]$ ]]; then
    echo "--pipe-index must be 0..9 or auto" >&2
    exit 1
  fi
  if ! start_relay "${PIPE_INDEX}"; then
    echo "Relay failed on discord-ipc-${PIPE_INDEX}. See /tmp/zp-discord-relay.log" >&2
    exit 1
  fi
fi

cleanup() {
  if [[ -n "${SERVICE_PID}" ]]; then
    if kill -0 "${SERVICE_PID}" >/dev/null 2>&1; then
      kill "${SERVICE_PID}" >/dev/null 2>&1 || true
      wait "${SERVICE_PID}" >/dev/null 2>&1 || true
    fi
  fi
  # Best-effort explicit clear while relay is still alive.
  ZP_CLEAR_CLIENT_ID="${CLIENT_ID}" ZP_CLEAR_SOCKET_PATH="${SOCKET_PATH}" \
    PYTHONPATH=src python3 -c 'import os; from zellij_presence.publishers.discord import DiscordRPCPublisher as D; cid=os.getenv("ZP_CLEAR_CLIENT_ID","").strip(); sp=os.getenv("ZP_CLEAR_SOCKET_PATH","").strip(); (D(cid, sp).close() if cid and sp else None)' \
    >/dev/null 2>&1 || true
  sleep 0.2
  if [[ -n "${RELAY_PID}" ]]; then
    kill "${RELAY_PID}" >/dev/null 2>&1 || true
    wait "${RELAY_PID}" >/dev/null 2>&1 || true
  fi
  rm -f "${SOCKET_PATH}"
}
trap cleanup EXIT INT TERM

echo "==> Starting zellij-presence with Discord enabled"
env PYTHONPATH=src python3 -m zellij_presence.cli run --verbose --config "${CONFIG_PATH}" &
SERVICE_PID=$!
wait "${SERVICE_PID}"
