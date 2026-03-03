#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TMP_PLUGIN_STATE="/tmp/zellij-plugin-state.json"
TMP_PLUGIN_CONFIG="/tmp/zellij-plugin.toml"
TMP_HTTP_CONFIG="/tmp/zellij-http.toml"
TMP_PLUGIN_OUTPUT="/tmp/zellij-presence-plugin.json"
TMP_HTTP_OUTPUT="/tmp/zellij-presence-http.json"
HTTP_PORT="48765"
HTTP_PID=""

cleanup() {
  if [[ -n "${HTTP_PID}" ]]; then
    kill "${HTTP_PID}" >/dev/null 2>&1 || true
    wait "${HTTP_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

run_with_timeout() {
  local seconds="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "${seconds}" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "${seconds}" "$@"
  else
    "$@"
  fi
}

can_bind_localhost() {
  set +e
  python3 - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.close()
except OSError:
    raise SystemExit(1)
PY
  local rc=$?
  set -e
  return "${rc}"
}

if [[ "${ZP_INSTALL_EDITABLE:-0}" == "1" ]]; then
  echo "==> Installing editable package"
  python3 -m pip install -e .
else
  echo "==> Skipping editable install (set ZP_INSTALL_EDITABLE=1 to enable)"
fi

echo "==> Running unit/integration tests"
PYTHONPATH=src python3 -m unittest discover -s tests -v

echo "==> CLI smoke: --help"
PYTHONPATH=src python3 -m zellij_presence.cli --help >/dev/null

echo "==> CLI smoke: status"
PYTHONPATH=src python3 -m zellij_presence.cli status >/dev/null

echo "==> CLI smoke: run --dry-run"
set +e
run_with_timeout 3s env PYTHONPATH=src python3 -m zellij_presence.cli run --dry-run >/dev/null
rc=$?
set -e
if [[ "$rc" -ne 0 && "$rc" -ne 124 ]]; then
  echo "dry-run smoke test failed (exit $rc)" >&2
  exit "$rc"
fi

echo "==> Plugin collector mode smoke"
cat >"${TMP_PLUGIN_STATE}" <<'EOF'
{"session_name":"plugin-live","tab_name":"editor","pane_title":"nvim","command":"nvim","cwd":"/tmp/project","collected_at":32503680000}
EOF

cat >"${TMP_PLUGIN_CONFIG}" <<'EOF'
safe_mode = false

[collector]
strategy = "plugin"
plugin_state_file = "/tmp/zellij-plugin-state.json"
plugin_max_age_seconds = 60.0

[publish]
file_path = "/tmp/zellij-presence-plugin.json"
http_enabled = false
http_host = "127.0.0.1"
http_port = 4765

[publish.discord]
enabled = false
client_id = ""
socket_path = ""

[filters]
allow_commands = ["nvim"]
deny_paths = []
redact_patterns = []
EOF

rm -f "${TMP_PLUGIN_OUTPUT}"
plugin_status="$(PYTHONPATH=src python3 -m zellij_presence.cli --config "${TMP_PLUGIN_CONFIG}" status)"
echo "${plugin_status}" | rg '"session_name": "plugin-live"' >/dev/null
echo "${plugin_status}" | rg '"command": "nvim"' >/dev/null

echo "==> HTTP publisher smoke"
if ! can_bind_localhost; then
  echo "Skipping HTTP smoke test: local socket bind not permitted in this environment"
  echo "==> All checks passed"
  exit 0
fi

cat >"${TMP_HTTP_CONFIG}" <<'EOF'
safe_mode = true

[collector]
strategy = "plugin"
plugin_state_file = "/tmp/zellij-plugin-state.json"
plugin_max_age_seconds = 60.0

[publish]
file_path = "/tmp/zellij-presence-http.json"
http_enabled = true
http_host = "127.0.0.1"
http_port = 48765

[publish.discord]
enabled = false
client_id = ""
socket_path = ""

[filters]
allow_commands = ["nvim"]
deny_paths = []
redact_patterns = []
EOF

rm -f "${TMP_HTTP_OUTPUT}"
env PYTHONPATH=src python3 -m zellij_presence.cli --config "${TMP_HTTP_CONFIG}" run >/dev/null 2>&1 &
HTTP_PID="$!"

http_payload=""
for _ in $(seq 1 20); do
  if command -v curl >/dev/null 2>&1; then
    if http_payload="$(curl -s "http://127.0.0.1:${HTTP_PORT}/presence" 2>/dev/null)"; then
      [[ -n "${http_payload}" ]] && break
    fi
  else
    set +e
    http_payload="$(python3 - <<PY
import urllib.request
try:
    print(urllib.request.urlopen("http://127.0.0.1:${HTTP_PORT}/presence", timeout=1).read().decode())
except Exception:
    pass
PY
)"
    py_rc=$?
    set -e
    if [[ "${py_rc}" -eq 0 && -n "${http_payload}" ]]; then
      break
    fi
  fi
  sleep 0.2
done

if [[ -z "${http_payload}" ]]; then
  echo "HTTP presence endpoint did not return payload" >&2
  exit 1
fi
echo "${http_payload}" | rg '"session_name":\s*"plugin-live"' >/dev/null

echo "==> All checks passed"
