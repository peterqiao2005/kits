#!/usr/bin/env bash
set -euo pipefail

# ========= 基本变量 =========
BASE_DIR="${HOME}/workspace/openvpn"
DATA_DIR="${BASE_DIR}/data"
COMPOSE_FILE="${BASE_DIR}/docker-compose.yml"
CLIENT_NAME="vpn-johor"
IMAGE="kylemanna/openvpn"
VPN_PORT="12294"
VPN_PROTO="udp4"   # 强制 IPv4
DOCKER_USER="--user $(id -u):$(id -g)"  # 关键：用当前用户写入数据卷
# =================================

mkdir -p "${DATA_DIR}"
if ! command -v docker >/dev/null 2>&1; then echo "ERROR: docker 未安装"; exit 1; fi
if command -v docker compose >/dev/null 2>&1; then DC="docker compose"; \
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"; \
else echo "ERROR: 未检测到 docker compose"; exit 1; fi

read -rp "请输入服务器公网 IP 或域名（如 1.2.3.4 或 vpn.example.com）: " PUBLIC_HOST
[[ -z "${PUBLIC_HOST}" ]] && { echo "ERROR: 不能为空"; exit 1; }

# docker-compose.yml（12294/udp + IPv6 sysctl）
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

# 生成配置（用当前用户写入）
docker run ${DOCKER_USER} --rm -v "${DATA_DIR}:/etc/openvpn" "${IMAGE}" \
  ovpn_genconfig -u "udp://${PUBLIC_HOST}:${VPN_PORT}"

# 初始化 PKI（当前用户写入）
if [[ ! -d "${DATA_DIR}/pki" ]]; then
  docker run ${DOCKER_USER} --rm -v "${DATA_DIR}:/etc/openvpn" -e EASYRSA_BATCH=1 "${IMAGE}" \
    ovpn_initpki nopass
fi

# 启一次让默认 openvpn.conf 就位，再停
${DC} -f "${COMPOSE_FILE}" up -d
sleep 2
${DC} -f "${COMPOSE_FILE}" stop || true

# 修 openvpn.conf（现在文件已经归你，不会 Permission denied）
touch "${DATA_DIR}/openvpn.conf"
sed -i -E '/^\s*comp-lzo\b/d;/^\s*compress\b/d' "${DATA_DIR}/openvpn.conf"

if grep -qE '^\s*proto\s+' "${DATA_DIR}/openvpn.conf"; then
  sed -i -E 's/^\s*proto\s+.*/proto '"${VPN_PROTO}"'/g' "${DATA_DIR}/openvpn.conf"
else
  echo "proto ${VPN_PROTO}" >> "${DATA_DIR}/openvpn.conf"
fi

if grep -qE '^\s*topology\s+' "${DATA_DIR}/openvpn.conf"; then
  sed -i -E 's/^\s*topology\s+.*/topology subnet/g' "${DATA_DIR}/openvpn.conf"
else
  echo "topology subnet" >> "${DATA_DIR}/openvpn.conf"
fi

sed -i -E '/^\s*mssfix\b/d' "${DATA_DIR}/openvpn.conf"
grep -qE '^\s*tun-mtu\s+' "${DATA_DIR}/openvpn.conf" || echo "tun-mtu 1400" >> "${DATA_DIR}/openvpn.conf"
grep -qE '^\s*explicit-exit-notify\b' "${DATA_DIR}/openvpn.conf" || echo "explicit-exit-notify 1" >> "${DATA_DIR}/openvpn.conf"

# 启动
${DC} -f "${COMPOSE_FILE}" up -d --force-recreate
sleep 3

# 开启 IPv4 转发
echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-openvpn.conf >/dev/null
sudo sysctl -p /etc/sysctl.d/99-openvpn.conf
cat /etc/sysctl.d/99-openvpn.conf | grep net.ipv4.ip_forward

# UFW 放行（如启用）
if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 12294/udp
  sudo ufw reload
  sudo ufw status | grep 12294 || true
fi

# 客户端证书与 ovpn（也用当前用户写入）
docker run ${DOCKER_USER} --rm -v "${DATA_DIR}:/etc/openvpn" "${IMAGE}" \
  easyrsa build-client-full "${CLIENT_NAME}" nopass || true
docker run ${DOCKER_USER} --rm -v "${DATA_DIR}:/etc/openvpn" "${IMAGE}" \
  ovpn_getclient "${CLIENT_NAME}" > "${BASE_DIR}/${CLIENT_NAME}.ovpn"

# 自检
echo "===== 服务端配置自检（应为 udp4 / subnet / 无压缩 / tun-mtu 1400）====="
cat "${DATA_DIR}/openvpn.conf" | grep -E '^(proto|topology|tun-mtu|mssfix|explicit-exit-notify|comp|compress)'
echo "===== 监听端口（应看到 :12294）====="
ss -lun | grep ':12294' || true
echo "===== 初始化完成日志 ====="
docker logs openvpn | grep -E 'Initialization Sequence Completed' || true
echo "===== 客户端 remote 行 ====="
cat "${BASE_DIR}/${CLIENT_NAME}.ovpn" | grep '^remote '

echo
echo "[DONE] 客户端文件：${BASE_DIR}/${CLIENT_NAME}.ovpn"
