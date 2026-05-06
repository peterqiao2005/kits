#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/root/workspace/vaultwarden-backup"
CRON_FILE="/etc/cron.d/vaultwarden-backup"
REQUIRED=(rsync ssh cron)
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

mkdir -p "$APP_DIR/backups" "$APP_DIR/logs" "$APP_DIR/ssh"
chmod 700 "$APP_DIR/backups" "$APP_DIR/ssh"
chmod 600 "$APP_DIR/ssh/id_ed25519" 2>/dev/null || true
chmod 644 "$APP_DIR/ssh/id_ed25519.pub" 2>/dev/null || true
chmod 755 "$APP_DIR/pull-backup.sh" "$APP_DIR/status.sh"

cat > "$CRON_FILE" <<CRON
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 5 * * * root $APP_DIR/pull-backup.sh >> $APP_DIR/logs/backup.log 2>&1
CRON
chmod 0644 "$CRON_FILE"
systemctl enable --now cron

echo "[INFO] 192.168.100.11 pull backup deployed under $APP_DIR"
echo "[INFO] Daily pull cron installed: 05:00"