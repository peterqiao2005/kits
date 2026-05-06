#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/root/workspace/vaultwarden-backup"
echo "[cron]"
cat /etc/cron.d/vaultwarden-backup 2>/dev/null || true
echo
echo "[backups on 100.11]"
ls -lah "$APP_DIR/backups" 2>/dev/null || true
echo
echo "[recent log]"
tail -n 100 "$APP_DIR/logs/backup.log" 2>/dev/null || true