#!/usr/bin/env bash
set -euo pipefail

CONFIG="/opt/rdp-kit/config/rdp_hosts.csv"

# 从 rdp_hosts.csv 的 vpn 列收集名字（去重，去掉 none）
declare -A VPNS=()

if [[ -r "$CONFIG" ]]; then
  while IFS=, read -r name host user pass size vpn sec; do
    [[ "$name" =~ ^# ]] && continue
    vpn=$(echo "$vpn" | tr -d '[:space:]')
    [[ -z "$vpn" || "$vpn" == "none" ]] && continue
    VPNS["$vpn"]=1
  done < <(grep -vE '^\s*#' "$CONFIG")
fi

# 同时把 /etc/openvpn/client/*.conf 也纳入（确保都可管理）
shopt -s nullglob
for f in /etc/openvpn/client/*.conf; do
  base="$(basename "$f")"
  vpn="${base%.conf}"
  [[ -n "$vpn" ]] && VPNS["$vpn"]=1
done

# 输出 Openbox pipe menu XML
echo '<openbox_pipe_menu>'

# 顶部通用操作
echo '  <item label="Stop ALL VPNs">'
echo '    <action name="Execute"><command>vpnctl.sh stop-all</command></action>'
echo '  </item>'

echo '  <item label="Show VPN Status (xterm)">'
echo '    <action name="Execute"><command>xterm -e bash -lc "vpnctl.sh status; echo; read -n1 -s -p PressAnyKey..."</command></action>'
echo '  </item>'

# 每条 VPN 的状态与操作
for vpn in "${!VPNS[@]}"; do
  svc="openvpn-client@${vpn}.service"
  # 取状态
  if systemctl is-active --quiet "$svc"; then
    state="[UP]"
    act_label="Disconnect"
    act_cmd="vpnctl.sh down ${vpn}"
  else
    state="[DOWN]"
    act_label="Connect (exclusive)"
    act_cmd="vpnctl.sh switch ${vpn}"
  fi

  echo "  <separator label=\"${vpn} ${state}\"/>"

  # 独占连接
  echo "  <item label=\"Connect ${vpn} (exclusive)\">"
  echo "    <action name=\"Execute\"><command>vpnctl.sh switch ${vpn}</command></action>"
  echo "  </item>"

  # 并存连接
  echo "  <item label=\"Connect ${vpn} (parallel)\">"
  echo "    <action name=\"Execute\"><command>vpnctl.sh up ${vpn}</command></action>"
  echo "  </item>"

  # 断开
  echo "  <item label=\"Disconnect ${vpn}\">"
  echo "    <action name=\"Execute\"><command>vpnctl.sh down ${vpn}</command></action>"
  echo "  </item>"

done

echo '</openbox_pipe_menu>'

