#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/root/workspace/vaultwarden-backup/restore-test"
BACKUP_DIR="/root/workspace/vaultwarden-backup/backups"
DATA_DIR="$APP_DIR/vw-data"
TLS_DIR="$APP_DIR/tls"
NGINX_CONF="$APP_DIR/nginx.conf"
VW_CONTAINER="vaultwarden-restore-test"
HTTPS_CONTAINER="vaultwarden-restore-https"
VW_IMAGE="vaultwarden/server:1.35.3"
NGINX_IMAGE="nginx:alpine"
HTTP_PORT="18080"
HTTPS_PORT="18443"
HOST_IP="192.168.100.11"

backup_file="${1:-}"
if [[ -z "$backup_file" ]]; then
  backup_file="$(ls -1t "$BACKUP_DIR"/*.tar.xz | head -1)"
fi

if [[ ! -f "$backup_file" ]]; then
  echo "[ERROR] Backup file not found: $backup_file" >&2
  exit 1
fi

if [[ $EUID -ne 0 ]]; then
  echo "[ERROR] Please run as root." >&2
  exit 1
fi

echo "[INFO] Restoring from: $backup_file"

if docker ps -a --format '{{.Names}}' | grep -qx "$HTTPS_CONTAINER"; then
  docker rm -f "$HTTPS_CONTAINER" >/dev/null
fi
if docker ps -a --format '{{.Names}}' | grep -qx "$VW_CONTAINER"; then
  docker rm -f "$VW_CONTAINER" >/dev/null
fi

stamp="$(date +%Y%m%d-%H%M%S)"
if [[ -d "$DATA_DIR" ]]; then
  mv "$DATA_DIR" "$APP_DIR/vw-data.before-restore-$stamp"
fi
install -d -m 0755 "$DATA_DIR"
tar -xJf "$backup_file" -C "$DATA_DIR"

# bruceforce/vaultwarden-backup archives files at the root. Older fallback
# backups may contain a data/ directory, so normalize both layouts.
if [[ -d "$DATA_DIR/data" ]]; then
  find "$DATA_DIR/data" -mindepth 1 -maxdepth 1 -exec mv -t "$DATA_DIR" {} +
  rmdir "$DATA_DIR/data"
fi

if [[ ! -f "$DATA_DIR/db.sqlite3" ]]; then
  echo "[ERROR] Restored data is missing db.sqlite3" >&2
  exit 1
fi
chmod 600 "$DATA_DIR/db.sqlite3" "$DATA_DIR"/rsa_key* 2>/dev/null || true

docker image inspect "$VW_IMAGE" >/dev/null 2>&1 || docker pull "$VW_IMAGE"
docker image inspect "$NGINX_IMAGE" >/dev/null 2>&1 || docker pull "$NGINX_IMAGE"

cat > "$APP_DIR/docker-compose.yml" <<YAML
services:
  vaultwarden-restore-test:
    image: $VW_IMAGE
    container_name: $VW_CONTAINER
    restart: unless-stopped
    ports:
      - "$HTTP_PORT:80"
    volumes:
      - ./vw-data:/data
    environment:
      DOMAIN: https://$HOST_IP:$HTTPS_PORT
      SIGNUPS_ALLOWED: "false"
      WEBSOCKET_ENABLED: "true"
YAML

cat > "$NGINX_CONF" <<'NGINX'
events {}
http {
  server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/nginx/certs/server.crt;
    ssl_certificate_key /etc/nginx/certs/server.key;
    client_max_body_size 128M;

    location / {
      proxy_pass http://host.docker.internal:18080;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto https;
    }

    location /notifications/hub {
      proxy_pass http://host.docker.internal:18080;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto https;
    }
  }
}
NGINX

install -d -m 0755 "$TLS_DIR"
if [[ ! -f "$TLS_DIR/server.key" || ! -f "$TLS_DIR/server.crt" ]]; then
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$TLS_DIR/server.key" \
    -out "$TLS_DIR/server.crt" \
    -subj "/CN=$HOST_IP" \
    -addext "subjectAltName=IP:$HOST_IP,DNS:localhost"
fi
chmod 600 "$TLS_DIR/server.key"
chmod 644 "$TLS_DIR/server.crt"

cd "$APP_DIR"
docker compose up -d 2>/dev/null || docker-compose up -d

docker run -d \
  --name "$HTTPS_CONTAINER" \
  --restart unless-stopped \
  --add-host=host.docker.internal:host-gateway \
  -p "$HTTPS_PORT:443" \
  -v "$NGINX_CONF:/etc/nginx/nginx.conf:ro" \
  -v "$TLS_DIR:/etc/nginx/certs:ro" \
  "$NGINX_IMAGE" >/dev/null

for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$HTTP_PORT/alive" >/dev/null 2>&1 && curl -k -fsS "https://127.0.0.1:$HTTPS_PORT/alive" >/dev/null 2>&1; then
    echo "[INFO] Restore test environment is healthy."
    break
  fi
  sleep 2
  if [[ "$i" == "30" ]]; then
    echo "[ERROR] Restore finished but health check did not pass." >&2
    docker ps -a --filter name='vaultwarden-restore' --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
    exit 1
  fi
done

echo "[INFO] HTTPS URL: https://$HOST_IP:$HTTPS_PORT"
docker ps -a --filter name='vaultwarden-restore' --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'