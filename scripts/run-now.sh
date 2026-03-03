#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONFIG_PATH="${ZP_CONFIG_PATH:-/tmp/zellij-presence.toml}"
OUTPUT_PATH="${ZP_OUTPUT_PATH:-/tmp/zellij-presence.json}"
DRY_RUN=1

usage() {
  cat <<'EOF'
Usage: bash scripts/run-now.sh [--no-dry-run] [--config /path/to/config.toml]

Options:
  --no-dry-run   Run normally (writes to configured output file).
  --config PATH  Override config path (default: /tmp/zellij-presence.toml).
Env:
  ZP_OUTPUT_PATH  Presence JSON output path (default: /tmp/zellij-presence.json).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-dry-run)
      DRY_RUN=0
      shift
      ;;
    --config)
      if [[ $# -lt 2 ]]; then
        echo "Missing value for --config" >&2
        exit 1
      fi
      CONFIG_PATH="$2"
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

echo "==> Initializing config at ${CONFIG_PATH}"
PYTHONPATH=src python3 -m zellij_presence.cli config init --path "${CONFIG_PATH}" --force

echo "==> Forcing collector.strategy = \"auto\" (plugin first, CLI fallback)"
if grep -q '^strategy = "' "${CONFIG_PATH}"; then
  sed -i 's/^strategy = ".*"/strategy = "auto"/' "${CONFIG_PATH}"
else
  cat >>"${CONFIG_PATH}" <<'EOF'

[collector]
strategy = "auto"
EOF
fi

echo "==> Forcing publish.file_path = ${OUTPUT_PATH}"
if grep -q '^file_path = "' "${CONFIG_PATH}"; then
  sed -i "s#^file_path = \".*\"#file_path = \"${OUTPUT_PATH}\"#" "${CONFIG_PATH}"
else
  cat >>"${CONFIG_PATH}" <<EOF

[publish]
file_path = "${OUTPUT_PATH}"
EOF
fi

echo "==> Starting zellij-presence"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  exec env PYTHONPATH=src python3 -m zellij_presence.cli run --verbose --config "${CONFIG_PATH}" --dry-run
else
  exec env PYTHONPATH=src python3 -m zellij_presence.cli run --verbose --config "${CONFIG_PATH}"
fi
