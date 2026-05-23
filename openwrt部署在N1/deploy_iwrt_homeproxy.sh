#!/usr/bin/env bash
set -euo pipefail

############################################
# 固定配置（按你的要求）
############################################
PARENT_IF="${PARENT_IF:-eth0}"

LAN_CIDR="${LAN_CIDR:-192.168.1.0/24}"
LAN_GW="${LAN_GW:-192.168.1.1}"
LAN_DNS="${LAN_DNS:-192.168.1.1}"

HOST_IP="${HOST_IP:-192.168.1.11}"
IWRT_IP="${IWRT_IP:-192.168.1.13}"

############################################
# 可覆盖配置
############################################
NET_NAME="${NET_NAME:-openwrt-macvlan}"     # 你机器上现有的 macvlan 网络名
CT_NAME="${CT_NAME:-immortalwrt}"
HOST_SHIM_IF="${HOST_SHIM_IF:-macvlan-shim0}"
HOST_SHIM_IP="${HOST_SHIM_IP:-192.168.1.250}"

IMAGE="${IMAGE:-lxiaya/openwrt-homeproxy:latest}"

############################################
# 基本检查（不破坏现有环境）
############################################
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: 请使用 root 运行"
  exit 1
fi

if ! ip link show "$PARENT_IF" >/dev/null 2>&1; then
  echo "ERROR: 未找到网卡 $PARENT_IF"
  ip link | sed -n '1,160p'
  exit 1
fi

# 不要改动宿主机 Docker 环境：只做检查
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found. 当前脚本不会安装 docker，以免破坏现有环境。"
  exit 1
fi

if ! docker version >/dev/null 2>&1; then
  echo "ERROR: docker exists but not working (docker version failed). 请先修复宿主机 docker。"
  exit 1
fi

if ! command -v ip >/dev/null 2>&1; then
  echo "ERROR: ip command not found (iproute2 missing). 当前脚本不自动安装包。"
  exit 1
fi

############################################
# 打开转发（旁路由必须；这是内核参数，不改包）
############################################
cat >/etc/sysctl.d/99-iwrt.conf <<EOF
net.ipv4.ip_forward=1
EOF
sysctl -p /etc/sysctl.d/99-iwrt.conf >/dev/null

############################################
# 确认 macvlan 网络存在（不创建新 pool，避免 overlaps）
############################################
if ! docker network inspect "$NET_NAME" >/dev/null 2>&1; then
  echo "ERROR: docker network not found: $NET_NAME"
  echo "现有网络："
  docker network ls
  exit 1
fi

############################################
# 创建宿主机 shim（否则宿主机可能访问不到 macvlan 容器）
############################################
if ! ip link show "$HOST_SHIM_IF" >/dev/null 2>&1; then
  ip link add "$HOST_SHIM_IF" link "$PARENT_IF" type macvlan mode bridge
  ip addr add "$HOST_SHIM_IP/${LAN_CIDR#*/}" dev "$HOST_SHIM_IF"
  ip link set "$HOST_SHIM_IF" up
fi

############################################
# 启动 ImmortalWrt + HomeProxy
############################################
docker pull "$IMAGE" >/dev/null

if docker ps -a --format '{{.Names}}' | grep -qx "$CT_NAME"; then
  docker rm -f "$CT_NAME" >/dev/null 2>&1 || true
fi

docker run -d \
  --name "$CT_NAME" \
  --restart unless-stopped \
  --network "$NET_NAME" \
  --ip "$IWRT_IP" \
  --privileged \
  "$IMAGE" /sbin/init >/dev/null

############################################
# 容器内网络配置：改 LAN 为 192.168.1.13/24 + 设置网关/DNS + 关闭 DHCP
############################################
echo "[INFO] Configure OpenWrt LAN IP/GW/DNS and disable DHCP inside container..."

# 等 init/procd 起完，避免 uci/network restart 时机太早
sleep 3

# 写 UCI + 重启服务（尽量幂等）
docker exec "$CT_NAME" /bin/sh -lc "
set -e

# 配置 LAN IP / netmask / gateway / dns
uci set network.lan.ipaddr='${IWRT_IP}'
uci set network.lan.netmask='255.255.255.0'
uci set network.lan.gateway='${LAN_GW}'
uci set network.lan.dns='${LAN_DNS}'
uci commit network

# 关闭 LAN DHCP，避免和主路由冲突
uci set dhcp.lan.ignore='1'

uci commit dhcp

# 重启网络与 dnsmasq
/etc/init.d/network restart >/dev/null 2>&1 || true
/etc/init.d/dnsmasq restart >/dev/null 2>&1 || true
" >/dev/null

############################################
# 基本验证
############################################
echo "[INFO] Verify connectivity inside container..."
docker exec "$CT_NAME" /bin/sh -lc "
ip a | grep -nE 'br-lan|inet '
ip r
ping -c 1 ${LAN_GW} >/dev/null 2>&1 && echo 'ping gateway OK' || echo 'ping gateway FAIL'
ping -c 1 8.8.8.8 >/dev/null 2>&1 && echo 'ping 8.8.8.8 OK' || echo 'ping 8.8.8.8 FAIL'
" || true

echo
echo "======================================"
echo "旁路由 IP: http://${IWRT_IP}/"
echo "宿主机 IP: ${HOST_IP}"
echo "Docker network: ${NET_NAME}"
echo "======================================"
echo
echo "宿主机测试："
echo "  ping -c 2 ${IWRT_IP}"
echo "  curl -I http://${IWRT_IP}/ | head"
echo
echo "进入 OpenWrt："
echo "  docker exec -it ${CT_NAME} /bin/sh"

