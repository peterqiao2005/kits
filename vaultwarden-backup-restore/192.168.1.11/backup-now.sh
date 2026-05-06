#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/root/workspace/vaultwarden-backup"
LOCAL_BACKUP_DIR="$APP_DIR/backups/local"
LOG_DIR="$APP_DIR/logs"
VW_CONTAINER="vaultwarden"
IMAGE="${IMAGE:-bruceforce/vaultwarden-backup:latest}"
RETENTION_DAYS="${RETENTION_DAYS:-0}"

mkdir -p "$LOCAL_BACKUP_DIR" "$LOG_DIR"

if ! docker inspect "$VW_CONTAINER" >/dev/null 2>&1; then
  echo "[ERROR] Docker container '$VW_CONTAINER' was not found." >&2
  exit 1
fi

run_id="$(date +%Y%m%d-%H%M%S)"
echo "[$(date '+%F %T')] Starting Docker vaultwarden-backup, run_id=$run_id, image=$IMAGE"

docker run --rm \
  --name "vaultwarden-backup-manual-$run_id" \
  --volumes-from="$VW_CONTAINER" \
  -e UID=0 \
  -e GID=0 \
  -e BACKUP_DIR=/backup \
  -e TIMESTAMP=true \
  -e TZ=Asia/Shanghai \
  -v "$LOCAL_BACKUP_DIR:/backup" \
  "$IMAGE" manual

if [[ "$RETENTION_DAYS" != "0" ]]; then
  find "$LOCAL_BACKUP_DIR" -type f \( -name '*.tar.xz' -o -name '*.tar.xz.gpg' \) -mtime +"$RETENTION_DAYS" -delete
fi

echo "[$(date '+%F %T')] Docker vaultwarden-backup completed"
ls -lah "$LOCAL_BACKUP_DIR"