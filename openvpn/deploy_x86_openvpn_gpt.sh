#!/usr/bin/env bash
set -euo pipefail

# === 可调参数 ===
PORT=${PORT:-18443}             # 对外端口（TCP）
CLIENT=${CLIENT:-vpn-johor}     # 客户端名
LAN_NET=${LAN_NET:-192.168.100.0/24}  # 需要通过 VPN 访问的内网网段
BASE="${HOME}/workspace/openvpn"
DATA="${BASE}/data"

# === 交互输入：公网域名或IP ===
if [[ "${OVPN_HOST:-}" == "" ]]; then
  read -rp "请输入服务器公网 IP 或域名（例如 vpn.example.com）: " OVPN_HOST
  [[ -z "$OVPN_HOST" ]] && { echo "不能为空"; exit 1; }
fi

echo "==> 使用域名/IP: $OVPN_HOST"
echo "==> 对外端口(TCP): $PORT"
echo "==> 推送内网路由:   $LAN_NET"
mkdir -p "$BASE" "$DATA"

# === 写 docker-compose.yml（TCP ${PORT} -> 容器 1194/tcp）===
cat > "${BASE}/docker-compose.yml" <<'YML'
services:
  openvpn:
    image: kylemanna/openvpn
    container_name: openvpn
    restart: unless-stopped
    ports:
      - "${PORT}:1194/tcp"
    volumes:
      - ./data:/etc/openvpn
    cap_add:
      - NET_ADMIN
    sysctls:
      - net.ipv6.conf.all.disable_ipv6=1
YML
sed -i -E "s/\${PORT}/${PORT}/g" "${BASE}/docker-compose.yml"

# === 生成基础配置（如已存在则跳过）===
if [[ ! -f "${DATA}/ovpn_env.sh" ]]; then
  echo "==> 生成 ovpn 基础配置 ..."
  docker run --rm -v "${DATA}:/etc/openvpn" kylemanna/openvpn \
    ovpn_genconfig \
      -u "tcp://${OVPN_HOST}:${PORT}" \
      -e "topology subnet"
fi

# 初始化 PKI（已有则不重复）
if [[ ! -d "${DATA}/pki" ]]; then
  echo "==> 初始化 PKI ..."
  docker run --rm -v "${DATA}:/etc/openvpn" \
    -e EASYRSA_BATCH=1 -e EASYRSA_REQ_CN="${OVPN_HOST}" \
    kylemanna/openvpn ovpn_initpki nopass
fi

# === 生成 tls-crypt 密钥（如未生成）===
if [[ ! -f "${DATA}/tls-crypt.key" ]]; then
  echo "==> 生成 tls-crypt.key ..."
  docker run --rm -v "${DATA}:/etc/openvpn" kylemanna/openvpn \
    openvpn --genkey --secret /etc/openvpn/tls-crypt.key
fi

# === 修正服务端配置 ===
CONF="${DATA}/openvpn.conf"
if [[ -f "$CONF" ]]; then
  echo "==> 修正服务端 openvpn.conf ..."

  # 统一参数与去除不需要的 push
  sudo sed -i -E '
    s/^\s*proto\s+.*/proto tcp-server/;
    s/^\s*topology\s+.*/topology subnet/;
    s/^\s*tun-mtu\s+.*/tun-mtu 1300/;
    /^\s*mssfix\b/d;
    /^\s*compress\b/d;
    /^\s*comp-lzo\b/d;
    /^\s*explicit-exit-notify\b/d;
    s/^\s*tls-auth\s+.*$/# &/;
    s/^\s*key-direction\s+.*$/# &/;
    /^\s*push\s+"?redirect-gateway\b/d;
    /^\s*push\s+"?dhcp-option\s+DNS\b/d;
    /^\s*push\s+"?block-outside-dns"?/d;
  ' "$CONF"

  # 追加必要项（不存在则追加）
  grep -qE '^\s*tls-crypt\s+' "$CONF" || echo 'tls-crypt tls-crypt.key'        | sudo tee -a "$CONF" >/dev/null
  grep -qE '^\s*mssfix\s+'     "$CONF" || echo 'mssfix 1200'                    | sudo tee -a "$CONF" >/dev/null
  grep -qE '^\s*verb\s+'       "$CONF" || echo 'verb 3'                         | sudo tee -a "$CONF" >/dev/null
  grep -qE '^\s*mute\s+'       "$CONF" || echo 'mute 20'                        | sudo tee -a "$CONF" >/dev/null
  grep -qE '^\s*duplicate-cn\b' "$CONF" || echo 'duplicate-cn'                  | sudo tee -a "$CONF" >/dev/null

  # 推送内网路由（从 LAN_NET 拆出地址与掩码，仅支持常见 /8 /16 /24 /32）
  NET="${LAN_NET%/*}"; PRE="${LAN_NET#*/}"
  case "$PRE" in
    8)  MASK="255.0.0.0" ;;
    16) MASK="255.255.0.0" ;;
    24) MASK="255.255.255.0" ;;
    32) MASK="255.255.255.255" ;;
    *)  echo "WARN: 不支持的掩码 /$PRE，默认按 /24 处理"; MASK="255.255.255.0" ;;
  esac
  if ! grep -qE "^\s*push\s+\"route\s+${NET}\s+${MASK}\"" "$CONF"; then
    echo "push \"route ${NET} ${MASK}\"" | sudo tee -a "$CONF" >/dev/null
  fi
fi

# === 启动/重启容器 ===
echo "==> 启动/重启 openvpn 容器 ..."
( cd "$BASE" && ( docker compose up -d --force-recreate || docker-compose up -d --force-recreate ) )

# === 生成/确认客户端证书 ===
echo "==> 生成/确认客户端证书: ${CLIENT}"
docker run --rm -v "${DATA}:/etc/openvpn" -e EASYRSA_BATCH=1 \
  kylemanna/openvpn easyrsa build-client-full "${CLIENT}" nopass || true

# === 导出客户端 ovpn 基础文件 ===
OVPN_OUT="${BASE}/${CLIENT}.ovpn"
echo "==> 导出客户端: ${OVPN_OUT}"
docker run --rm -v "${DATA}:/etc/openvpn" kylemanna/openvpn \
  ovpn_getclient "${CLIENT}" > "${OVPN_OUT}"

# === 客户端修正（仅 TCP/端口/MTU & 防压缩；不全局）===
echo "==> 修正客户端配置 ..."
sed -i -E "s/^proto\s+.*/proto tcp/; s/^remote\s+.*/remote ${OVPN_HOST} ${PORT} tcp/" "${OVPN_OUT}"
sed -i -E '/^\s*redirect-gateway\b/d' "${OVPN_OUT}"       # 确保不走全局
sed -i -E '/^\s*key-direction\b/d;/^\s*tls-auth\b/d' "${OVPN_OUT}"
sed -i '/<tls-auth>/,/<\/tls-auth>/d' "${OVPN_OUT}"
grep -qE '^tun-mtu '  "${OVPN_OUT}" || sed -i '1i tun-mtu 1300' "${OVPN_OUT}"
grep -qE '^mssfix '   "${OVPN_OUT}" || sed -i '1i mssfix 1200'  "${OVPN_OUT}"
grep -q 'pull-filter ignore "comp-lzo"'  "${OVPN_OUT}" || echo 'pull-filter ignore "comp-lzo"'  >> "${OVPN_OUT}"
grep -q 'pull-filter ignore "compress"'  "${OVPN_OUT}" || echo 'pull-filter ignore "compress"'  >> "${OVPN_OUT}"

# 嵌入 <tls-crypt>
if ! grep -q '<tls-crypt>' "${OVPN_OUT}"; then
  {
    echo '<tls-crypt>'
    docker run --rm -v "${DATA}:/etc/openvpn" kylemanna/openvpn cat /etc/openvpn/tls-crypt.key
    echo '</tls-crypt>'
  } >> "${OVPN_OUT}"
fi

# === UFW 放行 TCP 端口（如启用 UFW）===
if command -v ufw >/dev/null 2>&1; then
  echo "==> UFW 放行 ${PORT}/tcp（如已存在会忽略）"
  sudo ufw allow "${PORT}/tcp" >/dev/null 2>&1 || true
fi

# === 宿主机开启转发 + NAT（让客户端能访问 192.168.100.0/24 其它主机）===
echo "==> 开启转发并添加 NAT 回程 ..."
sudo bash -c 'echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-openvpn-forward.conf'
sudo sysctl -p /etc/sysctl.d/99-openvpn-forward.conf >/dev/null || true

# 计算 VPN 虚拟网段（kylemanna 默认 192.168.255.0/24；若将来改了请相应调整）
VPN_NET="192.168.255.0/24"

# 自动探测出站网卡
IFACE=$(ip -4 route show default 2>/dev/null | awk "/default/ {print \$5; exit}")
: "${IFACE:=eth0}"

# FORWARD 放行（双向）
sudo iptables -C FORWARD -s ${VPN_NET%/*}/24 -d "$LAN_NET" -j ACCEPT 2>/dev/null || \
sudo iptables -A FORWARD -s ${VPN_NET%/*}/24 -d "$LAN_NET" -j ACCEPT
sudo iptables -C FORWARD -s "$LAN_NET" -d ${VPN_NET%/*}/24 -j ACCEPT 2>/dev/null || \
sudo iptables -A FORWARD -s "$LAN_NET" -d ${VPN_NET%/*}/24 -j ACCEPT

# NAT：把来自 VPN 的访问伪装成宿主机内网 IP
sudo iptables -t nat -C POSTROUTING -s "$VPN_NET" -d "$LAN_NET" -o "$IFACE" -j MASQUERADE 2>/dev/null || \
sudo iptables -t nat -A POSTROUTING -s "$VPN_NET" -d "$LAN_NET" -o "$IFACE" -j MASQUERADE

# === 摘要输出 ===
echo
echo "================= 完成 ================="
echo "服务器：tcp://${OVPN_HOST}:${PORT}"
echo "配置目录：${DATA}"
echo "客户端文件：${OVPN_OUT}"
echo
echo "自检要点："
echo "  A) 日志应看到 TCP 监听与路由推送："
echo "     docker logs openvpn | egrep -i 'TCPv4_SERVER|PUSH_REPLY|Initialization' | tail -n 50"
echo "     —— 其中 PUSH_REPLY 里应含有 route ${LAN_NET}，且不含 redirect-gateway/dhcp-option DNS"
echo "  B) 客户端导入 ${OVPN_OUT} 连接后，目标网段走 VPN，本地上网直连。"
echo
echo "注意：iptables 规则是临时的，如需持久化可写入 /etc/rc.local 或 UFW before.rules。"
