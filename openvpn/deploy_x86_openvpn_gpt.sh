#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${HOME}/workspace/openvpn"
DATA_DIR="${BASE_DIR}/data"
COMPOSE_FILE="${BASE_DIR}/docker-compose.yml"
CLIENT_NAME="vpn-johor"
IMAGE="kylemanna/openvpn"

mkdir -p "${DATA_DIR}"

# 1) 确保 docker compose 存在
if command -v docker compose >/dev/null 2>&1; then DC="docker compose"; \
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"; \
else echo "ERROR: 未检测到 docker compose"; exit 1; fi

# 2) 备份
ts="$(date +%Y%m%d-%H%M%S)"
[[ -f "${DATA_DIR}/openvpn.conf" ]] && cp -a "${DATA_DIR}/openvpn.conf" "${DATA_DIR}/openvpn.conf.bak.${ts}"
[[ -f "${COMPOSE_FILE}" ]] && cp -a "${COMPOSE_FILE}" "${COMPOSE_FILE}.bak.${ts}"

# 3) 写/修 compose（端口12294 + IPv6 sysctl 消除告警）
cat > "${COMPOSE_FILE}" <<'YAML'
services:
  openvpn:
    image: kylemanna/openvpn
    container_name: openvpn
    restart: always
    cap_add:
      - NET_ADMIN
    sysctls:
      - net.ipv6.conf.default.forwarding=1
      - net.ipv6.conf.all.forwarding=1
    volumes:
      - ./data:/etc/openvpn
    ports:
      - "12294:1194/udp"
YAML

# 4) 启动一次确保 /etc/openvpn 文件就位，然后停掉以便修改
${DC} -f "${COMPOSE_FILE}" up -d || true
sleep 2
${DC} -f "${COMPOSE_FILE}" stop || true

# 5) 修 openvpn.conf 仅限必要项
touch "${DATA_DIR}/openvpn.conf"

# 去掉压缩
sed -i -E '/^\s*comp-lzo/d;/^\s*compress/d' "${DATA_DIR}/openvpn.conf"

# 强制 IPv4 UDP
if grep -qE '^\s*proto\s+' "${DATA_DIR}/openvpn.conf"; then
  sed -i -E 's/^\s*proto\s+.*/proto udp4/g' "${DATA_DIR}/openvpn.conf"
else
  echo "proto udp4" >> "${DATA_DIR}/openvpn.conf"
fi

# topology subnet
if grep -qE '^\s*topology\s+' "${DATA_DIR}/openvpn.conf"; then
  sed -i -E 's/^\s*topology\s+.*/topology subnet/g' "${DATA_DIR}/openvpn.conf"
else
  echo "topology subnet" >> "${DATA_DIR}/openvpn.conf"
fi

# MTU/MSS 防分片
grep -qE '^\s*mssfix\s+' "${DATA_DIR}/openvpn.conf" || echo "mssfix 1400" >> "${DATA_DIR}/openvpn.conf"
grep -qE '^\s*tun-mtu\s+' "${DATA_DIR}/openvpn.conf" || echo "tun-mtu 1400" >> "${DATA_DIR}/openvpn.conf"

# UDP 通知
grep -qE '^\s*explicit-exit-notify' "${DATA_DIR}/openvpn.conf" || echo "explicit-exit-notify 1" >> "${DATA_DIR}/openvpn.conf"

# 6) 重启并查看关键日志
${DC} -f "${COMPOSE_FILE}" up -d --force-recreate
sleep 3
docker logs --since=2m openvpn | tail -n +1

# 7) 重新导出客户端配置并清理压缩字段
docker run --rm -v "${DATA_DIR}:/etc/openvpn" "${IMAGE}" ovpn_getclient "${CLIENT_NAME}" > "${BASE_DIR}/${CLIENT_NAME}.ovpn"
sed -i -E '/^\s*comp-lzo/d;/^\s*compress/d' "${BASE_DIR}/${CLIENT_NAME}.ovpn"

echo
echo "[OK] 已修复。客户端文件：${BASE_DIR}/${CLIENT_NAME}.ovpn"
echo "下一步：请用新的 vpn-johor.ovpn 连接重测。"
echo
echo "快速校验："
echo "cat ${DATA_DIR}/openvpn.conf | grep -E '^(proto|topology|mssfix|tun-mtu|comp|compress)'"
echo "docker logs openvpn | grep -E 'Initialization Sequence Completed|PUSH_REPLY|topology|comp-lzo'"
