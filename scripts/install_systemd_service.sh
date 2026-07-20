#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
ENV_FILE="${HOME}/.config/hermes-bridge.env"
SERVICE_FILE="${SYSTEMD_USER_DIR}/hermes-bridge.service"

mkdir -p "${SYSTEMD_USER_DIR}"

cp "${SCRIPT_DIR}/../examples/systemd/hermes-bridge.service" "${SERVICE_FILE}"
sed -i "s|%h|${HOME}|g" "${SERVICE_FILE}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Creating example env file at ${ENV_FILE}"
    cp "${SCRIPT_DIR}/../examples/bridge.env.example" "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
fi

systemctl --user daemon-reload
systemctl --user enable hermes-bridge

echo "Service installed at ${SERVICE_FILE}"
echo "Edit ${ENV_FILE} then run: systemctl --user start hermes-bridge"
