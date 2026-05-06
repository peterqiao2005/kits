#!/usr/bin/env bash
set -euo pipefail
docker rm -f vaultwarden-restore-test 2>/dev/null || true
