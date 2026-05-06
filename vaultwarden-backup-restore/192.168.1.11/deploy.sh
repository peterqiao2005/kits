#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/root/workspace/vaultwarden-backup"
IMAGE="${IMAGE:-bruceforce/vaultwarden-backup:latest}"
REQUIRED=(docker tar)
MISSING=()

if [[ $EUID -ne 0 ]]; then
  echo "[ERROR] Please run as root." >&2
  exit 1
fi

for cmd in "${REQUIRED[@]}"; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    MISSING+=("$cmd")
  fi
done

if (( ${#MISSING[@]} > 0 )); then
  echo "[ERROR] Missing dependencies: ${MISSING[*]}" >&2
  exit 1
fi

mkdir -p "$APP_DIR/backups/local" "$APP_DIR/logs" "$APP_DIR/source"
chmod 755 "$APP_DIR/backup-local.sh" "$APP_DIR/backup-now.sh" "$APP_DIR/status.sh"
rm -f /etc/cron.d/vaultwarden-backup

if ! docker inspect vaultwarden >/dev/null 2>&1; then
  echo "[ERROR] Docker container 'vaultwarden' was not found." >&2
  exit 1
fi

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE"

echo "[INFO] 192.168.1.11 Docker vaultwarden-backup scripts deployed under $APP_DIR"
echo "[INFO] Scheduling is handled by 192.168.100.11 pulling over VPN."