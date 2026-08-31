#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Defaults
REMOTE_HOST="root@192.168.100.11"
REMOTE_DIR="/root/portal-console"
FRONTEND_PORT="5001"
USE_LOCAL_IMAGES=false
LOCAL_DIR="$SCRIPT_DIR"
IMAGE_TAR="$LOCAL_DIR/portal-console-images.tar"
SSH_COMMAND="ssh"
RSYNC_EXCLUDES=(
  --exclude='.git'
  --exclude='backend/data'
  --exclude='frontend/node_modules'
  --exclude='node_modules'
  --exclude='__pycache__'
  --exclude='portal-console-images.tar'
)

usage() {
  cat <<EOF
Usage: $0 [--remote user@host] [--port FRONTEND_PORT] [--use-local-images] [--help]

Examples:
  $0                                 # deploy to root@192.168.100.11, frontend on 5001
  $0 --remote root@192.168.1.11
  $0 --remote root@192.168.1.11 --port 5002
  $0 --remote root@192.168.1.11 --use-local-images
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote|-r)
      REMOTE_HOST="$2"
      shift 2
      ;;
    --port|-p)
      FRONTEND_PORT="$2"
      shift 2
      ;;
    --use-local-images)
      USE_LOCAL_IMAGES=true
      shift
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

if [ -n "${SSHPASS:-}" ]; then
  SSH_COMMAND="sshpass -p ${SSHPASS} ssh -o StrictHostKeyChecking=no"
  export RSYNC_RSH="sshpass -p ${SSHPASS} ssh -o StrictHostKeyChecking=no"
fi

if [ ! -f "$LOCAL_DIR/.env" ]; then
  echo "ERROR: .env not found in $LOCAL_DIR"
  exit 1
fi

if [ "$USE_LOCAL_IMAGES" = true ]; then
  echo "Building local images for backend and frontend..."
  docker compose build backend frontend
  echo "Saving local images to $IMAGE_TAR..."
  docker save portal-console-backend:latest portal-console-frontend:latest -o "$IMAGE_TAR"
fi

echo "Syncing local project to $REMOTE_HOST:$REMOTE_DIR..."
rsync -av --delete "${RSYNC_EXCLUDES[@]}" "$LOCAL_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"

if [ "$USE_LOCAL_IMAGES" = true ]; then
  echo "Syncing local image tar to remote host..."
  rsync -av "$IMAGE_TAR" "$REMOTE_HOST:$REMOTE_DIR/"
fi

REMOTE_CMDS=$(cat <<EOF
set -euo pipefail
cd ${REMOTE_DIR}
if [ ! -f docker-compose.override.yml ]; then
  cat > docker-compose.override.yml <<YML
services:
  frontend:
    ports:
      - "${FRONTEND_PORT}:80"
YML
  echo "Created docker-compose.override.yml to expose frontend on port ${FRONTEND_PORT}."
else
  python3 - <<PY
import re
from pathlib import Path
p = Path('docker-compose.override.yml')
text = p.read_text()
pattern = r'(^\s*frontend:\n(?:\s+.*\n)*?)(\s*ports:\n(?:\s+-\s*\".*\"\n)*)'
if re.search(pattern, text, flags=re.MULTILINE):
    text = re.sub(pattern, lambda m: m.group(1) + '    ports:\n      - "%s:80"\n' % ('${FRONTEND_PORT}'), text, flags=re.MULTILINE)
else:
    if 'frontend:' in text:
        text = text.replace('frontend:', 'frontend:\n  ports:\n      - "%s:80"' % ('${FRONTEND_PORT}'))
    else:
        text += '\nservices:\n  frontend:\n    ports:\n      - "%s:80"\n' % ('${FRONTEND_PORT}')
Path('docker-compose.override.yml').write_text(text)
PY
  echo "Updated docker-compose.override.yml with port ${FRONTEND_PORT}."
fi

if [ "${USE_LOCAL_IMAGES}" = "true" ]; then
  if [ -f portal-console-images.tar ]; then
    echo "Loading local images on remote host..."
    docker load < portal-console-images.tar
    rm -f portal-console-images.tar
  else
    echo "Warning: portal-console-images.tar not found on remote host"
  fi
  docker compose up -d --no-build
else
  docker compose up -d --build
fi
EOF
)

echo "Restarting remote compose stack on ${REMOTE_HOST}..."
if [ "$SSH_COMMAND" != "ssh" ]; then
  eval "$SSH_COMMAND \"$REMOTE_HOST\" \"$REMOTE_CMDS\""
else
  ssh "$REMOTE_HOST" "$REMOTE_CMDS"
fi

HOST_ONLY="${REMOTE_HOST#*@}"
echo "Deployment complete. Frontend should be available at http://$HOST_ONLY:${FRONTEND_PORT}"
