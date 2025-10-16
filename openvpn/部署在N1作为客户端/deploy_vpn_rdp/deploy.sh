#!/usr/bin/env bash
set -euo pipefail

: "${APP_ROOT:=$(pwd)}"
: "${CONFIG_DIR:=$APP_ROOT/config}"
: "${INSTALL_ROOT:=/opt/rdp-kit}"
: "${LOCAL_USER:=${SUDO_USER:-$USER}}"
: "${VPN_MODE:=exclusive}"    # exclusive=切换模式; parallel=并存模式

echo "[INFO] APP_ROOT=$APP_ROOT"
echo "[INFO] CONFIG_DIR=$CONFIG_DIR"
echo "[INFO] INSTALL_ROOT=$INSTALL_ROOT"
echo "[INFO] LOCAL_USER=$LOCAL_USER"
echo "[INFO] VPN_MODE=$VPN_MODE"

# 1. 安装依赖
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  openvpn xserver-xorg-video-fbdev xinit openbox \
  xserver-xorg-input-evdev xserver-xorg-input-libinput \
  whiptail freerdp3-x11

# 2. 安装脚本
install -d -m 0755 /usr/local/bin
if [[ -d "$APP_ROOT/bin" ]]; then
  install -m 0755 "$APP_ROOT/bin/"* /usr/local/bin/
fi

# 3. 保存配置副本
install -d -m 0755 "$INSTALL_ROOT"
rsync -a --delete "$CONFIG_DIR/" "$INSTALL_ROOT/config/"

# 4. Xorg fbdev 配置
if [[ -f "$CONFIG_DIR/99-fbdev.conf" ]]; then
  install -d -m 0755 /etc/X11/xorg.conf.d
  install -m 0644 "$CONFIG_DIR/99-fbdev.conf" /etc/X11/xorg.conf.d/99-fbdev.conf
fi

# 5. RDP 主机清单
if [[ -f "$CONFIG_DIR/rdp_hosts.csv" ]]; then
  install -m 0600 "$CONFIG_DIR/rdp_hosts.csv" "$INSTALL_ROOT/rdp_hosts.csv"
fi

# 6. OpenVPN 配置
install -d -m 0755 /etc/openvpn/client
shopt -s nullglob
for f in "$CONFIG_DIR"/*.ovpn; do
  base="$(basename "$f")"
  name="${base%.ovpn}"
  target="/etc/openvpn/client/${name}.conf"
  install -m 0600 "$f" "$target"
  svc="openvpn-client@${name}.service"
  systemctl enable "$svc" >/dev/null 2>&1 || true
  if [[ "$VPN_MODE" == "parallel" ]]; then
    systemctl start "$svc" || true
  else
    systemctl stop "$svc" || true
  fi
done

# 7. Openbox 菜单合入
user_home="$(eval echo ~"$LOCAL_USER")"
if [[ -d "$user_home" ]]; then
  install -d -m 0755 "$user_home/.config/openbox"
  menu_file="$user_home/.config/openbox/menu.xml"
  if [[ ! -f "$menu_file" ]]; then
    cp /etc/xdg/openbox/menu.xml "$menu_file"
    chown "$LOCAL_USER":"$LOCAL_USER" "$menu_file"
  fi
  if [[ -f "$CONFIG_DIR/menu_patch.xml" ]]; then
    if ! grep -q 'rdp-menu.sh' "$menu_file"; then
      tmpfile="$(mktemp)"
      awk '
        /<\/menu>/ && ++n==1 { system("cat '"$CONFIG_DIR/menu_patch.xml"'"); }
        { print }
      ' "$menu_file" >"$tmpfile"
      mv "$tmpfile" "$menu_file"
      chown "$LOCAL_USER":"$LOCAL_USER" "$menu_file"
    fi
  fi
fi

echo "[INFO] 部署完成，可以执行 rdp-menu.sh"

