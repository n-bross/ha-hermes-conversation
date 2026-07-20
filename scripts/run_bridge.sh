#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${SCRIPT_DIR}/.."
VENV="${ROOT}/bridge/.venv"

if [[ ! -d "${VENV}" ]]; then
    python3 -m venv "${VENV}"
fi

"${VENV}/bin/pip" install -q -r "${ROOT}/bridge/requirements.txt"

cd "${ROOT}/bridge"

HOST="${HERMES_BRIDGE_HOST:-127.0.0.1}"
PORT="${HERMES_BRIDGE_PORT:-8787}"

echo "Starting Hermes bridge on ${HOST}:${PORT}"
"${VENV}/bin/uvicorn" app:app --host "${HOST}" --port "${PORT}"
