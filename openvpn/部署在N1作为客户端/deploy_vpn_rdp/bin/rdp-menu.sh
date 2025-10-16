#!/usr/bin/env bash
set -euo pipefail

CSV="/opt/rdp-kit/config/rdp_hosts.csv"

if [[ ! -r "$CSV" ]]; then
  echo "Missing $CSV"; exit 1
fi

# 构造选择列表：name (host/vpn)
mapfile -t OPTIONS < <(grep -vE '^\s*#' "$CSV" | \
  awk -F',' 'NF>=7{gsub(/^[ \t]+|[ \t]+$/, "", $0); print $1" " "(" $2 "/" $6 ")"}')

CHOICE=$(whiptail --title "RDP Hosts" --menu "Select host" 20 70 10 \
  "${OPTIONS[@]}" 3>&1 1>&2 2>&3) || exit 1

LINE=$(grep -vE '^\s*#' "$CSV" | awk -F',' -v sel="$CHOICE" '$1==sel{print; exit}')
[[ -n "$LINE" ]] || { echo "Selection not found"; exit 1; }

NAME=$(echo "$LINE" | awk -F',' '{print $1}')
HOST=$(echo "$LINE" | awk -F',' '{print $2}')
USER=$(echo "$LINE" | awk -F',' '{print $3}')
PASS=$(echo "$LINE" | awk -F',' '{print $4}')
SIZE=$(echo "$LINE" | awk -F',' '{print $5}')
VPN=$( echo "$LINE" | awk -F',' '{print $6}')
SEC=$( echo "$LINE" | awk -F',' '{print $7}')

# 若密码为空，则运行时输入（不落盘）
if [[ -z "${PASS// }" ]]; then
  PASS=$(whiptail --passwordbox "Password for ${USER}@${HOST}" 8 60 3>&1 1>&2 2>&3) || exit 1
fi

# VPN：按“独占切换”处理（如需并存，把 switch 改成 up）
if [[ "$VPN" != "none" ]]; then
  /usr/local/bin/vpnctl.sh switch "$VPN"
fi

export DISPLAY=${DISPLAY:-:0}
SEC_OPT="/sec:${SEC:-nla}"
ARGS="/u:${USER} /p:${PASS} /v:${HOST} /size:${SIZE} /cert-ignore ${SEC_OPT} /network:lan /compression /gfx:RFX"

/usr/bin/xfreerdp ${ARGS}

