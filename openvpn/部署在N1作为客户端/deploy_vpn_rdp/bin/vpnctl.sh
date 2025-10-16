#!/usr/bin/env bash
set -euo pipefail

svc() { echo "openvpn-client@$1.service"; }

usage() {
  echo "Usage: vpnctl.sh list|status|up <name>|down <name>|switch <name>|stop-all"
}

cmd=${1:-}
case "$cmd" in
  list)
    systemctl list-unit-files | grep -E '^openvpn-client@' | cat
    ;;
  status)
    systemctl list-units --type=service | grep -E 'openvpn-client@' | cat
    ;;
  up)
    name=${2:?}
    systemctl start "$(svc "$name")"
    systemctl status "$(svc "$name")" | cat
    ;;
  down)
    name=${2:?}
    systemctl stop "$(svc "$name")"
    systemctl status "$(svc "$name")" | cat
    ;;
  stop-all)
    systemctl list-units --type=service | awk '/openvpn-client@/ {print $1}' | \
      xargs -r -n1 systemctl stop
    systemctl list-units --type=service | grep openvpn-client@ | cat
    ;;
  switch)
    name=${2:?}
    systemctl list-units --type=service | awk '/openvpn-client@/ {print $1}' | \
      grep -v "$(svc "$name")" | xargs -r -n1 systemctl stop
    systemctl start "$(svc "$name")"
    systemctl status "$(svc "$name")" | cat
    ;;
  *)
    usage; exit 1;;
esac

