#!/usr/bin/env bash
set -euo pipefail

# ===== 变量 =====
USER_NAME="${USER}"
HOME_DIR="/home/${USER_NAME}"
[[ -d "${HOME_DIR}" ]] || HOME_DIR="$HOME"
BASE="${HOME_DIR}/workspace/openvpn"
DATA="${BASE}/data"
COMPOSE="${BASE}/docker-compose.yml"
KIT_DIR="${HOME_DIR}/workspace/kits/openvpn"     # 你的部署脚本所在目录
DEPLOY_SH="${KIT_DIR}/deploy_x86_openvpn_gpt.sh" # 你的部署脚本文件名（如不同请改）
ROOT_BASE="/root/workspace/openvpn"

echo "[1/6] 停掉并删除旧容器（仅容器，不删数据）"
docker rm -f openvpn >/dev/null 2>&1 || true

echo "[2/6] 迁移 root 路径下的数据到当前用户目录（若存在）"
if [[ -d "${ROOT_BASE}/data" ]]; then
  sudo rsync -a "${ROOT_BASE}/" "${BASE}/"
fi

echo "[3/6] 修复目录所有权 + 设置 ACL，保证以后即便容器(root)写入你也能改"
sudo mkdir -p "${DATA}"
sudo chown -R "${USER_NAME}:${USER_NAME}" "${HOME_DIR}/workspace"
# 安装 ACL 工具
sudo apt-get update -y && sudo apt-get install -y acl
# 赋予你对 data 目录的读写执行权限，并设为默认 ACL（新文件也继承）
sudo setfacl -R -m u:${USER_NAME}:rwx "${DATA}"
sudo setfacl -R -d -m u:${USER_NAME}:rwx "${DATA}"
# 验证（按你要求用 cat|grep 风格）
getfacl "${DATA}" | grep -E "user:${USER_NAME}|default:user:${USER_NAME}"

echo "[4/6] 校验 compose 文件是否存在；不存在就创建一个（12294/udp + IPv6 sysctl）"
if [[ ! -f "${COMPOSE}" ]]; then
  mkdir -p "${BASE}"
  cat > "${COMPOSE}" <<'YAML'
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
fi
cat "${COMPOSE}" | grep -E '12294:1194/udp|sysctls|volumes'

echo "[5/6] 重新执行你的部署脚本（非 sudo；会提示输入公网域名/IP）"
# 注意：这里不再用 sudo bash；如果你必须提权，请用：sudo -E env HOME="$HOME" USER="$USER" bash "$DEPLOY_SH"
bash "${DEPLOY_SH}"

echo "[6/6] 部署后自检（不再用 grep 屏蔽真实错误）"
cd "${BASE}"
docker compose ps
ss -lun | grep ':12294' || true
echo "===== 最近200行原始日志 ====="
docker logs --tail 200 openvpn || true
echo "===== 关键配置检查 ====="
cat "${DATA}/openvpn.conf" | grep -E '^(proto|topology|tun-mtu|mssfix|comp|compress|explicit-exit-notify)'
echo "===== 客户端 remote 行 ====="
cat "${BASE}/vpn-johor.ovpn" | grep '^remote ' || true

echo
echo "[DONE] 如果上面日志里看到 'Initialization Sequence Completed'，就可以在客户端用 ${BASE}/vpn-johor.ovpn 连接了。"
