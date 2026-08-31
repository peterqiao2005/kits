#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Defaults
REMOTE_HOST="root@192.168.100.11"
REMOTE_DIR="/root/portal-console"
LOCAL_DIR="$SCRIPT_DIR"

usage() {
  cat <<EOF
Usage: $0 [--remote user@host] [--help]

Syncs backend/data directory (including SQLite database and SSH keys) to remote host.

Examples:
  $0                              # sync to root@192.168.100.11
  $0 --remote root@192.168.1.11
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote|-r)
      REMOTE_HOST="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

DATA_DIR="$LOCAL_DIR/backend/data"

if [ ! -d "$DATA_DIR" ]; then
  echo "ERROR: backend/data directory not found at $DATA_DIR"
  exit 1
fi

echo "Syncing backend/data to $REMOTE_HOST:$REMOTE_DIR/backend/data..."
rsync -av \
  --delete \
  "$DATA_DIR/" \
  "$REMOTE_HOST:$REMOTE_DIR/backend/data/"

echo "Data sync complete."
echo ""
echo "Note: If the remote Docker containers are running, restart them to pick up new data:"
echo "  ssh $REMOTE_HOST 'cd $REMOTE_DIR && docker compose restart backend'"
