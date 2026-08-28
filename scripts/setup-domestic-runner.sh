#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="${REPO_OWNER:-Anthony-0721}"
REPO_NAME="${REPO_NAME:-LawWatch}"
RUNNER_NAME="${RUNNER_NAME:-lawwatch-domestic}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,linux,x64,lawwatch-domestic}"
RUNNER_VERSION="${RUNNER_VERSION:-2.327.1}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
RUNNER_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}"

if [ -z "${RUNNER_TOKEN:-}" ]; then
  echo "ERROR: set RUNNER_TOKEN to the registration token from GitHub repo Settings > Actions > Runners." >&2
  exit 1
fi

for cmd in git python3 curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: missing command: $cmd" >&2
    exit 1
  fi
done

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

ARCHIVE="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
if [ ! -f "$ARCHIVE" ]; then
  curl -fL -o "$ARCHIVE" "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${ARCHIVE}"
fi
tar -xzf "$ARCHIVE"

./config.sh \
  --url "$RUNNER_URL" \
  --token "$RUNNER_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --unattended

if [ "$(id -u)" -eq 0 ]; then
  ./svc.sh install
  ./svc.sh start
  echo "Runner installed as a service and started."
else
  echo "Runner configured. Run './run.sh' in a terminal, or rerun as root to install it as a service."
fi

echo "Runner URL: $RUNNER_URL"
echo "Labels: $RUNNER_LABELS"
