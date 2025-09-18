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
# =================================

# 0) 环境与目录
mkdir -p "${DATA_DIR}"
if ! command -v docker >/dev/null 2>&1; then echo "ERROR: docker 未安装"; exit 1; fi
if command -v docker compose >/dev/null 2>&1; then DC="docker compose"; \
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"; \
else echo "ERROR: 未检测到 docker compose"; exit 1; fi

# 1) 询问公网地址或域名（供客户端 remote 使用）
read -rp "请输入服务器公网 IP 或域名（如 1.2.3.4 或 vpn.example.com）: " PUBLIC_HOST
if [[ -z "${PUBLIC_HOST}" ]]; then echo "ERROR: 不能为空"; exit 1; fi

# 2) 写入 docker-compose.yml（12294/udp + IPv6 sysctl）
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

# 3) 初始化服务端配置与 PKI
#    3.1 生成服务器URL配置（带端口）
docker run --rm -v "${DATA_DIR}:/etc/openvpn" "${IMAGE}" \
  ovpn_genconfig -u "udp://${PUBLIC_HOST}:${VPN_PORT}"

#    3.2 初始化 PKI（若已存在则跳过）
if [[ ! -d "${DATA_DIR}/pki" ]]; then
  docker run --rm -v "${DATA_DIR}:/etc/openvpn" -e EASYRSA_BATCH=1 "${IMAGE}" \
    ovpn_initpki nopass
fi

# 4) 启动一次容器让默认 openvpn.conf 就位，再停
${DC} -f "${COMPOSE_FILE}" up -d
sleep 2
${DC} -f "${COMPOSE_FILE}" stop || true

# 5) 修正 openvpn.conf（只改必要项）
#    - 禁用压缩
#    - proto 改为 udp4
#    - topology subnet
#    - MTU 防分片：tun-mtu 1400（不加 mssfix，避免警告）
#    - UDP 退出通知
touch "${DATA_DIR}/openvpn.conf"
sed -i -E '/^\s*comp-lzo/d;/^\s*compress/d' "${DATA_DIR}/openvpn.conf"
if grep -qE '^\s*proto\s+' "${DATA_DIR}/openvpn.conf"; then
  sed -i -E 's/^\s*proto\s+.*/proto udp4/g' "${DATA_DIR}/openvpn.conf"
else
  echo "proto udp4" >> "${DATA_DIR}/openvpn.conf"
fi
if grep -qE '^\s*topology\s+' "${DATA_DIR}/openvpn.conf"; then
  sed -i -E 's/^\s*topology\s+.*/topology subnet/g' "${DATA_DIR}/openvpn.conf"
else
  echo "topology subnet" >> "${DATA_DIR}/openvpn.conf"
fi
grep -qE '^\s*tun-mtu\s+' "${DATA_DIR}/openvpn.conf" || echo "tun-mtu 1400" >> "${DATA_DIR}/openvpn.conf"
grep -qE '^\s*explicit-exit-notify' "${DATA_DIR}/openvpn.conf" || echo "explicit-exit-notify 1" >> "${DATA_DIR}/openvpn.conf"

# 6) 再次启动容器
${DC} -f "${COMPOSE_FILE}" up -d --force-recreate
sleep 3

# 7) 开启 IPv4 转发（宿主机）
echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-openvpn.conf >/dev/null
sudo sysctl -p /etc/sysctl.d/99-openvpn.conf
# 验证：
cat /etc/sysctl.d/99-openvpn.conf | grep net.ipv4.ip_forward

# 8) UFW 放行 12294/udp（若启用）
if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 12294/udp
  sudo ufw reload
  sudo ufw status | grep 12294 || true
fi

# 9) 生成/覆盖客户端文件 vpn-johor.ovpn（与当前 ta.key 保持一致）
docker run --rm -v "${DATA_DIR}:/etc/openvpn" "${IMAGE}" \
  easyrsa build-client-full "${CLIENT_NAME}" nopass || true
docker run --rm -v "${DATA_DIR}:/etc/openvpn" "${IMAGE}" \
  ovpn_getclient "${CLIENT_NAME}" > "${BASE_DIR}/${CLIENT_NAME}.ovpn"

# 10) 自检：服务端配置与日志关键项
echo "===== 服务端配置自检（应为 udp4 / subnet / 无压缩 / tun-mtu 1400）====="
cat "${DATA_DIR}/openvpn.conf" | grep -E '^(proto|topology|tun-mtu|mssfix|explicit-exit-notify|comp|compress)'
echo "===== 监听端口（应看到 :12294）====="
ss -lun | grep ':12294' || true
echo "===== 启动完成日志（应包含 Initialization Sequence Completed）====="
docker logs openvpn | grep -E 'Initialization Sequence Completed|PUSH_REPLY|topology|comp-lzo' || true

# 11) 客户端文件自检
echo "===== 客户端文件自检（remote 应为 ${PUBLIC_HOST} ${VPN_PORT}）====="
cat "${BASE_DIR}/${CLIENT_NAME}.ovpn" | grep -E '^(remote|proto|key-direction|tls-crypt|tls-auth)'
cat "${BASE_DIR}/${CLIENT_NAME}.ovpn" | grep -Ei 'comp-lzo|compress' || echo "[OK] 客户端无压缩参数"

echo
echo "[DONE] OpenVPN 已启动。客户端文件：${BASE_DIR}/${CLIENT_NAME}.ovpn"
echo "使用该文件在 OpenVPN GUI / Tunnelblick / Linux openvpn 客户端导入连接即可。"
