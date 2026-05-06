#!/usr/bin/env bash
set -euo pipefail
docker ps -a --filter name=vaultwarden-restore-test --format 'table {{.Names}}	{{.Image}}	{{.Ports}}	{{.Status}}'
echo
curl -fsS http://127.0.0.1:18080/alive && echo || true
echo
ls -lah /root/workspace/vaultwarden-backup/restore-test/vw-data
