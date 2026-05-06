#!/usr/bin/env bash
set -euo pipefail
APP_DIR="/root/workspace/vaultwarden-backup"
echo "[vaultwarden mount]"
docker inspect vaultwarden --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}' 2>/dev/null || true
echo "[backup image]"
docker images bruceforce/vaultwarden-backup 2>/dev/null || true
echo "[local backups]"
ls -lah "$APP_DIR/backups/local" 2>/dev/null || true
echo
echo "[recent log]"
tail -n 120 "$APP_DIR/logs/backup.log" 2>/dev/null || true