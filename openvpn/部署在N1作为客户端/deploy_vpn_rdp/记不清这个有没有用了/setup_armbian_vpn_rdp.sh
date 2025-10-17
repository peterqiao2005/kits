#!/usr/bin/env bash
set -euo pipefail

### ======= 可按需修改的参数（也可通过环境变量传入） =======
: "${RDP_USER:=Administrator}"     # 远程 Windows 用户名
: "${RDP_PASS:=ChangeMe123!}"      # 远程 Windows 密码
: "${RDP_HOST:=192.168.1.100}"     # 远程 Windows IP/主机名
: "${RDP_FULL:=1}"                 # 1=全屏 / 0=窗口
: "${LOCAL_USER:=${SUDO_USER:-$USER}}"   # 本机登录的普通用户名（用于自动登录 & 运行 RDP）
: "${OVPN_FILE:=/root/client.ovpn}"      # 你的 .ovpn 文件路径
: "${OVPN_NAME:=myvpn}"                  # systemd 实例名，生成 openvpn-client@myvpn.service
### ===============================================

if [[ $EUID -ne 0 ]]; then
  echo "请用 root 运行：sudo bash $0"
  exit 1
fi

echo "[1/8] apt 更新并安装组件（不会执行 upgrade）..."
apt update
DEBIAN_FRONTEND=noninteractive apt install -y \
  openvpn xorg lxde-core lightdm freerdp3-x11

echo "[2/8] 配置 OpenVPN 客户端..."
install -d -m 0755 /etc/openvpn/client
if [[ ! -f "$OVPN_FILE" ]]; then
  echo "未找到 OVPN 文件：$OVPN_FILE"
  echo "请先把你的 client.ovpn 放到：$OVPN_FILE 然后重试"
  exit 1
fi
cp -f "$OVPN_FILE" "/etc/openvpn/client/${OVPN_NAME}.conf"
chmod 600 "/etc/openvpn/client/${OVPN_NAME}.conf"

echo "[3/8] 强化 OpenVPN 与网络顺序（drop-in）..."
install -d -m 0755 /etc/systemd/system/openvpn-client@.service.d
cat >/etc/systemd/system/openvpn-client@.service.d/override.conf <<'EOF'
[Unit]
Wants=network-online.target
After=network-online.target

[Service]
# 避免重启风暴
Restart=always
RestartSec=5
EOF

systemctl daemon-reload
systemctl enable "openvpn-client@${OVPN_NAME}.service"

echo "[4/8] 配置 LightDM 自动登录到本地用户：$LOCAL_USER ..."
install -d -m 0755 /etc/lightdm/lightdm.conf.d
cat >/etc/lightdm/lightdm.conf.d/12-autologin.conf <<EOF
[Seat:*]
autologin-user=$LOCAL_USER
autologin-user-timeout=0
session-wrapper=/etc/X11/Xsession
user-session=LXDE
EOF

echo "[5/8] 写入 RDP 启动脚本 /usr/local/bin/autordp.sh ..."
cat >/usr/local/bin/autordp.sh <<EOF
#!/usr/bin/env bash
set -euo pipefail
# 等待 VPN/网络微调
sleep 5
export DISPLAY=:0

RDP_USER="${RDP_USER}"
RDP_PASS="${RDP_PASS}"
RDP_HOST="${RDP_HOST}"
RDP_FULL="${RDP_FULL}"

ARGS="/u:\${RDP_USER} /p:\${RDP_PASS} /v:\${RDP_HOST} /cert-ignore /rfx /network:auto /compression /gfx:RFX /sound:sys:alsa"
if [[ "\${RDP_FULL}" == "1" ]]; then
  ARGS="\${ARGS} /f"
fi

# 如果远端启用 NLA，FreeRDP 会自动协商；如需指定可加：/sec:nla
# 如需指定分辨率，替代 /f 为：/size:1920x1080

# 遇到异常时循环重连，避免服务退出
while true; do
  xfreerdp \${ARGS} || true
  sleep 3
done
EOF
chmod +x /usr/local/bin/autordp.sh
chown "$LOCAL_USER":"$LOCAL_USER" /usr/local/bin/autordp.sh

echo "[6/8] 创建 systemd 服务 autordp.service（依赖 VPN 与图形）..."
cat >/etc/systemd/system/autordp.service <<EOF
[Unit]
Description=Auto RDP (start after VPN & GUI)
After=lightdm.service openvpn-client@${OVPN_NAME}.service
Requires=openvpn-client@${OVPN_NAME}.service

[Service]
Type=simple
User=${LOCAL_USER}
Environment=DISPLAY=:0
ExecStart=/usr/local/bin/autordp.sh
Restart=always
RestartSec=5

[Install]
WantedBy=graphical.target
EOF

systemctl daemon-reload
systemctl enable autordp.service

echo "[7/8] 设置默认目标为图形界面（确保进到 lightdm）..."
systemctl set-default graphical.target

echo "[8/8] 立即启动 VPN 与 RDP 服务（可选）..."
systemctl start "openvpn-client@${OVPN_NAME}.service" || true
# 等 2 秒再启 RDP，避免初次抓日志误判
sleep 2
systemctl start autordp.service || true

echo
echo "=== 完成 ==="
echo "VPN 实例：openvpn-client@${OVPN_NAME}.service"
echo "RDP 服务：autordp.service"
echo
echo "重启后流程：先连 VPN -> LightDM 自动登录 -> autordp 启动并全屏连接 RDP"
echo
echo "如需修改 RDP 用户/密码/地址：vim /usr/local/bin/autordp.sh"
echo "如需替换 OVPN：vim /etc/openvpn/client/${OVPN_NAME}.conf"
echo
echo "现在可用以下命令自检："
echo "  systemctl status openvpn-client@${OVPN_NAME}.service | cat"
echo "  journalctl -u openvpn-client@${OVPN_NAME}.service -n 50 | cat"
echo "  systemctl status autordp.service | cat"
echo "  journalctl -u autordp.service -n 50 | cat"
