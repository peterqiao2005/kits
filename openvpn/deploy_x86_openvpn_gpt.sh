#!/usr/bin/env bash
set -euo pipefail

# -------- 基本变量 --------
BASE_DIR="${HOME}/workspace/openvpn"
DATA_DIR="${BASE_DIR}/data"
COMPOSE_FILE="${BASE_DIR}/docker-compose.yml"
CLIENT_NAME="vpn-johor"
VPN_PORT="12294"          # 宿主机端口
VPN_PROTO="udp"           # 协议
IMAGE="kylemanna/openvpn"

# -------- 1) 目录与 docker compose 检查 --------
mkdir -p "${DATA_DIR}"
if command -v docker >/dev/null 2>&1; then
  :
else
  echo "ERROR: 未检测到 docker，请先安装 docker。"
  exit 1
fi
if command -v docker compose >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "ERROR: 未检测到 docker compose，请先安装（Docker v2: docker compose / Docker v1: docker-compose）。"
  exit 1
fi

# -------- 2) 写入 docker-compose.yml --------
cat > "${COMPOSE_FILE}" <<'YAML'
services:
  openvpn:
    image: kylemanna/openvpn
    container_name: openvpn
    restart: always
    cap_add:
      - NET_ADMIN
    volumes:
      - ./data:/etc/openvpn
    ports:
      - "12294:1194/udp"
    # 如果宿主机或网络策略限制 icmp，可取消注释以下环境变量以避免 healthcheck 问题
    # environment:
    #   - OVPN_NATDEVICE=eth0
YAML

echo "[OK] 已生成 ${COMPOSE_FILE}"

# -------- 3) 询问公网地址或域名（用于生成配置）--------
read -rp "请输入服务器公网 IP 或域名（给客户端连接用，例如 1.2.3.4 或 vpn.example.com）: " PUBLIC_HOST
if [[ -z "${PUBLIC_HOST}" ]]; then
  echo "ERROR: 不能为空。"
  exit 1
fi

# -------- 4) 生成 OpenVPN 基本配置 --------
# 将服务端地址与端口写入配置（例如 udp://vpn.example.com:12294）
docker run --rm -v "${DATA_DIR}:/etc/openvpn" "${IMAGE}" \
  ovpn_genconfig -u "${VPN_PROTO}://${PUBLIC_HOST}:${VPN_PORT}"

# -------- 5) 初始化 PKI（非交互 & 无密码）--------
# EASYRSA_BATCH=1 关闭交互，'nopass' 使 CA/服务端证书无密码，适合自动化部署
docker run --rm -v "${DATA_DIR}:/etc/openvpn" -e EASYRSA_BATCH=1 "${IMAGE}" \
  ovpn_initpki nopass

# -------- 6) 开启 IP 转发（永久 & 即时生效）--------
echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-openvpn.conf >/dev/null
sudo sysctl -p /etc/sysctl.d/99-openvpn.conf
# 按你的偏好：直接用命令检查而不是口头描述
cat /etc/sysctl.d/99-openvpn.conf | grep net.ipv4.ip_forward

# -------- 7) UFW（若启用则放行 12294/udp）--------
if command -v ufw >/dev/null 2>&1; then
  if sudo ufw status | grep -q "Status: active"; then
    sudo ufw allow "${VPN_PORT}"/udp
    sudo ufw reload
    # 检查规则
    sudo ufw status | grep "${VPN_PORT}/udp" || true
  fi
fi

# -------- 8) 启动容器 --------
cd "${BASE_DIR}"
${DC} up -d
${DC} ps

# -------- 9) 生成客户端证书与配置（无密码）--------
docker run --rm -v "${DATA_DIR}:/etc/openvpn" -e EASYRSA_BATCH=1 "${IMAGE}" \
  easyrsa build-client-full "${CLIENT_NAME}" nopass

# 导出 client ovpn 到工作区
docker run --rm -v "${DATA_DIR}:/etc/openvpn" "${IMAGE}" \
  ovpn_getclient "${CLIENT_NAME}" > "${BASE_DIR}/${CLIENT_NAME}.ovpn"

# -------- 10) 结果输出 --------
echo
echo "[DONE] OpenVPN 已部署并启动。"
echo "客户端配置文件：${BASE_DIR}/${CLIENT_NAME}.ovpn"
echo "服务端监听：${PUBLIC_HOST}:${VPN_PORT}/${VPN_PROTO}"
echo
echo "日志查看：${DC} -f ${COMPOSE_FILE} logs -f openvpn"
