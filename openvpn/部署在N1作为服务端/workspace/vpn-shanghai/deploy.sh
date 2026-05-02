#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD=python
else
    echo "python3 or python was not found in PATH" >&2
    exit 1
fi

CRON_LINE="*/30 * * * * cd \"$SCRIPT_DIR\" && $PYTHON_CMD openvpn_auto_ip_update.py >> openvpn_ip_update.log 2>&1"

(crontab -l 2>/dev/null | grep -v 'openvpn_auto_ip_update.py'; echo "$CRON_LINE") | crontab -

echo "Installed crontab:"
crontab -l | grep 'openvpn_auto_ip_update.py'
