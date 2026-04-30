#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CRON_LINE="*/30 * * * * cd \"$SCRIPT_DIR\" && python openvpn_auto_ip_update.py >> openvpn_ip_update.log 2>&1"

(crontab -l 2>/dev/null | grep -v 'openvpn_auto_ip_update.py'; echo "$CRON_LINE") | crontab -

echo "Installed crontab:"
crontab -l | grep 'openvpn_auto_ip_update.py'
