#!/bin/bash
set -e

# 依赖确认（已装会跳过）
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-xdg menu dbus-x11 >/dev/null 2>&1 || true

# 生成 debian 菜单（第一次可能没有）
update-menus || true

# 若 :0 没有在跑，则启动 openbox
if ! pgrep -f 'Xorg :0' >/dev/null 2>&1; then
  echo "[INFO] start openbox on :0 ..."
  nohup xinit /usr/bin/openbox-session -- :0 -keeptty >/tmp/openbox.xinit.log 2>&1 &
  # 等待 X 就绪
  for i in {1..10}; do
    sleep 1
    if xdpyinfo -display :0 >/dev/null 2>&1; then
      break
    fi
  done
fi

# 启动 x11vnc（如已在跑则跳过）
if ! pgrep -f 'x11vnc.*-display :0' >/dev/null 2>&1; then
  echo "[INFO] start x11vnc on :0 ..."
  nohup x11vnc -display :0 -auth /root/.Xauthority -rfbauth /root/.vnc/passwd -forever -shared >/tmp/x11vnc.log 2>&1 &
fi

echo "[OK] Openbox + x11vnc ready. Connect to: <IP>:5900"

