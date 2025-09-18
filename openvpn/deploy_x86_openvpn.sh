#!/usr/bin/env bash
set -euo pipefail

# ========== 变量 ==========
IMAGE="kylemanna/openvpn"
CONTAINER="openvpn"
TARGET_USER="${SUDO_USER:-$USER}"
TARGET_HOME="/home/${TARGET_USER}"
[[ -d "${TARGET_HOME}" ]] || TARGET_HOME="$HOME"
TARGET_BASE="${TARGET_HOME}/workspace/openvpn"
TARGET_DATA="${TARGET_BASE}/data"
TARGET_COMPOSE="${TARGET_BASE}/docker-compose.yml"
CLIENT_NAME="vpn-johor"

# ========== 0) 查容器实际数据目录/端口 ==========
echo "[i] 检查容器挂载与端口 ..."
SRC_DATA="$(docker inspect ${CONTAINER} --format '{{range .Mounts}}{{if eq .Destination "/etc/openvpn"}}{{.Source}}{{end}}{{end}}' || true)"
PORTS="$(docker inspect ${CONTAINER} --format '{{json .HostConfig.PortBindings}}' || true)"
echo "  当前容器数据目录: ${SRC_DATA:-<未发现>}"
echo "  端口映射: ${PORTS}"

# ========== 1) 打印最近200行原始日志（不要grep）==========
echo "[i] 容器最近200行日志（用于定位Restarting原因）:"
docker logs --tail 200 ${CONTAINER} || true
echo "---------------------------------------------"

# ========== 2) 统一到 ~/workspace/openvpn 路径 ==========
echo "[i] 停止并移除旧容器（仅容器，数据不删）..."
docker rm -f ${CONTAINER} >/dev/null 2>&1 || true

echo "[i] 创建目标目录: ${TARGET_DATA}"
mkdir -p "${TARGET_DATA}"

if [[ -n "${SRC_DATA}" && "${SRC_DATA}" != "${TARGET_DATA}" && -d "${SRC_DATA}" ]]; then
  echo "[i] 迁移数据: ${SRC_DATA} -> ${TARGET_DATA}"
  sudo rsync -a --delete "${SRC_DATA}/" "${TARGET_DATA}/"
fi

echo "[i] 目录所有权修复为 ${TARGET_USER}:${TARGET_USER}"
sudo chown -R "${TARGET_USER}:${TARGET_USER}" "${TARGET_HOME}/workspace" || true

# ========== 3) 写入统一的 docker-compose.yml （12294/udp + IPv6 sysctl）==========
cat > "${TARGET_COMPOSE}" <<'YAML'
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

# ========== 4) 强制修正 openvpn.conf 仅必要项 ==========
touch "${TARGET_DATA}/openvpn.conf"

# 删除压缩
sed -i -E '/^\s*comp-lzo\b/d;/^\s*compress\b/d' "${TARGET_DATA}/openvpn.conf"

# proto -> udp4
if grep -qE '^\s*proto\s+' "${TARGET_DATA}/openvpn.conf"; then
  sed -i -E 's/^\s*proto\s+.*/proto udp4/g' "${TARGET_DATA}/openvpn.conf"
else
  echo "proto udp4" >> "${TARGET_DATA}/openvpn.conf"
fi

# topology -> subnet
if grep -qE '^\s*topology\s+' "${TARGET_DATA}/openvpn.conf"; then
  sed -i -E 's/^\s*topology\s+.*/topology subnet/g' "${TARGET_DATA}/openvpn.conf"
else
  echo "topology subnet" >> "${TARGET_DATA}/openvpn.conf"
fi

# MTU 收紧且无 mssfix 警告
sed -i -E '/^\s*mssfix\b/d' "${TARGET_DATA}/openvpn.conf"
grep -qE '^\s*tun-mtu\s+' "${TARGET_DATA}/openvpn.conf" || echo "tun-mtu 1400" >> "${TARGET_DATA}/openvpn.conf"
grep -qE '^\s*explicit-exit-notify' "${TARGET_DATA}/openvpn.conf" || echo "explicit-exit-notify 1" >> "${TARGET_DATA}/openvpn.conf"

echo "[i] 服务端关键配置："
cat "${TARGET_DATA}/openvpn.conf" | grep -E '^(proto|topology|tun-mtu|mssfix|comp|compress|explicit-exit-notify)'

# ========== 5) 启动容器（在目标目录）==========
cd "${TARGET_BASE}"
if command -v docker compose >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
${DC} -f "${TARGET_COMPOSE}" up -d --force-recreate

# ========== 6) 系统转发 & UFW ==========
echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-openvpn.conf >/dev/null
sudo sysctl -p /etc/sysctl.d/99-openvpn.conf >/dev/null
cat /etc/sysctl.d/99-openvpn.conf | grep net.ipv4.ip_forward

if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 12294/udp
  sudo ufw reload >/dev/null
  sudo ufw status | grep 12294 || true
fi

# ========== 7) 导出客户端文件（统一放在 ~/workspace/openvpn/）==========
docker run --rm -v "${TARGET_DATA}:/etc/openvpn" ${IMAGE} ovpn_getclient "${CLIENT_NAME}" > "${TARGET_BASE}/${CLIENT_NAME}.ovpn"
sed -i -E '/^\s*comp-lzo\b/d;/^\s*compress\b/d' "${TARGET_BASE}/${CLIENT_NAME}.ovpn"

echo "[i] 客户端 remote 行："
cat "${TARGET_BASE}/${CLIENT_NAME}.ovpn" | grep -E '^remote '

# ========== 8) 打印完整启动日志，确认是否仍有错误 ==========
echo "===== 最近200行原始日志（不做grep，直接看错误）====="
docker logs --tail 200 ${CONTAINER} || true
echo "===== 监听端口（应看到 :12294）====="
ss -lun | grep ':12294' || true

echo
echo "[DONE] 统一到 ${TARGET_BASE} 并重启完成。客户端文件：${TARGET_BASE}/${CLIENT_NAME}.ovpn"
