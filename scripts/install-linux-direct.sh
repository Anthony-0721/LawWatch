#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run this script with sudo or as root." >&2
  exit 1
fi

APP_DIR="${APP_DIR:-/opt/lawwatch/app}"
VENV_DIR="${VENV_DIR:-/opt/lawwatch/venv}"
DATA_DIR="${DATA_DIR:-/var/lib/lawwatch}"
CONFIG_DIR="${CONFIG_DIR:-/etc/lawwatch}"
RUN_USER="${RUN_USER:-lawwatch}"
SERVICE_NAME="${SERVICE_NAME:-lawwatch-monitor}"
INSTALL_BROWSER="${INSTALL_BROWSER:-1}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! id "${RUN_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "/opt/lawwatch" --shell /usr/sbin/nologin "${RUN_USER}"
fi

mkdir -p "${APP_DIR}" "${VENV_DIR}" "${DATA_DIR}/logs" "${CONFIG_DIR}"

echo "Installing system packages..."
apt-get update
apt-get install -y git python3 python3-venv python3-pip curl

echo "Copying application files..."
rm -rf "${APP_DIR}/monitor"
cp -a "${SOURCE_DIR}/monitor" "${APP_DIR}/monitor"
cp -a "${SOURCE_DIR}/requirements.txt" "${APP_DIR}/requirements.txt"
rm -f "${APP_DIR}/monitor/state.json"
find "${APP_DIR}/monitor" -type d -name "__pycache__" -prune -exec rm -rf {} +

echo "Creating Python virtual environment..."
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

if [[ "${INSTALL_BROWSER}" == "1" ]]; then
  echo "Installing Chromium for Playwright..."
  "${VENV_DIR}/bin/python" -m playwright install --with-deps chromium
else
  echo "Skipping Chromium installation; dynamic sites will fall back to HTTP."
fi

if [[ -f "${DATA_DIR}/sites.csv" ]]; then
  echo "Preserving existing ${DATA_DIR}/sites.csv"
else
  cp -a "${APP_DIR}/monitor/sites.csv" "${DATA_DIR}/sites.csv"
  echo "Created ${DATA_DIR}/sites.csv"
fi

if [[ -f "${CONFIG_DIR}/config.json" ]]; then
  echo "Preserving existing ${CONFIG_DIR}/config.json"
else
  cp -a "${SOURCE_DIR}/linux/config.example.json" "${CONFIG_DIR}/config.json"
  echo "Created ${CONFIG_DIR}/config.json from template"
fi

chmod 750 "${CONFIG_DIR}"
chmod 640 "${CONFIG_DIR}/config.json"
chown -R root:"${RUN_USER}" "${CONFIG_DIR}"
chown -R "${RUN_USER}":"${RUN_USER}" "${APP_DIR}" "${DATA_DIR}"

install -m 0644 "${SOURCE_DIR}/linux/systemd/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"
install -m 0644 "${SOURCE_DIR}/linux/systemd/${SERVICE_NAME}.timer" "/etc/systemd/system/${SERVICE_NAME}.timer"
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.timer"

echo
echo "Installation complete."
echo "1. Edit ${CONFIG_DIR}/config.json to add email/WeCom credentials."
echo "2. Test once: sudo -u ${RUN_USER} ${VENV_DIR}/bin/python -m monitor.run --test-notification --config ${CONFIG_DIR}/config.json --data-dir ${DATA_DIR}"
echo "3. Check status: systemctl status ${SERVICE_NAME}.timer"
echo "4. Check logs: journalctl -u ${SERVICE_NAME} -n 200 --no-pager"
