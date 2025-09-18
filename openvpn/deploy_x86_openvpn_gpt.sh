#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${HOME}/workspace/openvpn"
DATA_DIR="${BASE_DIR}/data"
COMPOSE_FILE="${BASE_DIR}/docker-compose.yml"
CLIENT_NAME="vpn-johor"

# 1) 基本检查
if ! command -v docker >/dev/null 2>&1; then echo "docker 未安装"; exit 1; fi
if command -v docker compose >/dev/null 2>&1; then DC="docker compose"; \
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"; \
else echo "未检测到 docker compose"; exit 1; fi
mkdir -p "${DATA_DIR}"

# 2) 备份当前配置
ts="$(date +%Y%m%d-%H%M%S)"
if [[ -f "${DATA_DIR}/openvpn.conf" ]]; then
  cp -a "${DATA_DIR}/openvpn.conf" "${DATA_DIR}/openvpn.conf.bak.${ts}"
fi
if [[ -f "${COMPOSE_FILE}" ]]; then
  cp -a "${COMPOSE_FILE}" "${COMPOSE_FILE}.bak.${ts}"
fi

# 3) 生成/覆盖 docker-compose.yml（保留数据卷）
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

echo "[OK] compose 已写入：${COMPOSE_FILE}"
# 检查端口映射
cat "${COMPOSE_FILE}" | grep "12294:1194/udp"

# 4) 修补服务端 openvpn.conf（禁压缩、subnet 拓扑、mssfix、udp4）
# 若文件不存在，容器启动后会生成；我们先停容器，确保文件写入后再改
${DC} -f "${COMPOSE_FILE}" up -d || true
sleep 2
${DC} -f "${COMPOSE_FILE}" stop || true

# 确保配置文件存在（若不存在先创建一个最小骨架，随后由镜像入口脚本补齐）
if [[ ! -f "${DATA_DIR}/openvpn.conf" ]]; then
  touch "${DATA_DIR}/openvpn.conf"
fi

# 删除/注释 comp-lzo / compress 相关行
sed -i -E 's/^\s*comp-lzo.*$/# comp-lzo disabled/g' "${DATA_DIR}/openvpn.conf" || true
sed -i -E 's/^\s*compress.*$/# compress disabled/g' "${DATA_DIR}/openvpn.conf" || true

# 强制使用 udp4，减少 IPv6 干扰
if grep -qE '^\s*proto\s+udp\s*$' "${DATA_DIR}/openvpn.conf"; then
  sed -i -E 's/^\s*proto\s+udp\s*$/proto udp4/g' "${DATA_DIR}/openvpn.conf"
elif ! grep -qE '^\s*proto\s+udp4' "${DATA_DIR}/openvpn.conf"; then
  echo "proto udp4" >> "${DATA_DIR}/openvpn.conf"
fi

# 设置 topology subnet
if grep -qE '^\s*topology\s+' "${DATA_DIR}/openvpn.conf"; then
  sed -i -E 's/^\s*topology\s+.*/topology subnet/g' "${DATA_DIR}/openvpn.conf"
else
  echo "topology subnet" >> "${DATA_DIR}/openvpn.conf"
fi

# 限制 MSS，减少分片
grep -qE '^\s*mssfix\s+' "${DATA_DIR}/openvpn.conf" || echo "mssfix 1400" >> "${DATA_DIR}/openvpn.conf"

# UDP 下建议显式退出通知
grep -qE '^\s*explicit-exit-notify' "${DATA_DIR}/openvpn.conf" || echo "explicit-exit-notify 1" >> "${DATA_DIR}/openvpn.conf"

echo "[OK] 已修补 ${DATA_DIR}/openvpn.conf"
# 检查关键项
cat "${DATA_DIR}/openvpn.conf" | grep -E 'proto|topology|mssfix|comp|compress|explicit-exit-notify' || true

# 5) 启动并重建容器
${DC} -f "${COMPOSE_FILE}" up -d --force-recreate
sleep 2
${DC} -f "${COMPOSE_FILE}" ps
docker logs --since=2m openvpn | tail -n +1

# 6) 重新导出客户端配置（确保客户端无压缩指令）
if docker ps --format '{{.Names}}' | grep -q '^openvpn$'; then
  docker run --rm -v "${DATA_DIR}:/etc/openvpn" kylemanna/openvpn ovpn_getclient "${CLIENT_NAME}" > "${BASE_DIR}/${CLIENT_NAME}.ovpn"
  # 二次确认客户端文件不存在压缩配置
  sed -i -E '/^\s*comp-lzo/d;/^\s*compress/d' "${BASE_DIR}/${CLIENT_NAME}.ovpn"
  echo "[OK] 客户端文件已导出：${BASE_DIR}/${CLIENT_NAME}.ovpn"
  cat "${BASE_DIR}/${CLIENT_NAME}.ovpn" | grep -E 'comp|compress' || echo "[OK] 客户端无压缩参数"
else
  echo "容器未在运行，跳过导出客户端。"
fi

# 7) 内核转发（之前已做过仍再次确保）
echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-openvpn.conf >/dev/null
sudo sysctl -p /etc/sysctl.d/99-openvpn.conf
cat /etc/sysctl.d/99-openvpn.conf | grep net.ipv4.ip_forward

# 8) UFW 放行（如启用）
if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 12294/udp
  sudo ufw reload
  sudo ufw status | grep "12294/udp" || true
fi

echo
echo "[DONE] 修复完成，请用新的客户端文件重连：${BASE_DIR}/${CLIENT_NAME}.ovpn"
echo "追日志：docker logs -f openvpn | grep -E 'Initialization|AUTH|comp|topology|MSS|MTU|ERROR'"
