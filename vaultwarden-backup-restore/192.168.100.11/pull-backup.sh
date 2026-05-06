#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/root/workspace/vaultwarden-backup"
BACKUP_DIR="$APP_DIR/backups"
LOG_DIR="$APP_DIR/logs"
SSH_KEY="$APP_DIR/ssh/id_ed25519"
SOURCE_HOST="192.168.1.11"
SOURCE_USER="root"
SOURCE_APP_DIR="/root/workspace/vaultwarden-backup"
SOURCE_BACKUP_DIR="$SOURCE_APP_DIR/backups/local"

mkdir -p "$BACKUP_DIR" "$LOG_DIR"
chmod 700 "$BACKUP_DIR"

echo "[$(date '+%F %T')] Triggering Vaultwarden backup on $SOURCE_HOST"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$SOURCE_USER@$SOURCE_HOST" "$SOURCE_APP_DIR/backup-local.sh >> $SOURCE_APP_DIR/logs/backup.log 2>&1"

echo "[$(date '+%F %T')] Pulling backups from $SOURCE_HOST:$SOURCE_BACKUP_DIR"
rsync -av --chmod=F600,D700 -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new" "$SOURCE_USER@$SOURCE_HOST:$SOURCE_BACKUP_DIR/" "$BACKUP_DIR/"

echo "[$(date '+%F %T')] Pull backup completed into $BACKUP_DIR"