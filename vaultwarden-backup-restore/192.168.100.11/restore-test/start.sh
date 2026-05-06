#!/usr/bin/env bash
set -euo pipefail
cd /root/workspace/vaultwarden-backup/restore-test
docker compose up -d 2>/dev/null || docker-compose up -d
