cat > check_wake_service.sh <<'BASH'
#!/usr/bin/env bash
set -euo pipefail

SVC_NAME="wake.service"
SVC_PATH="/etc/systemd/system/${SVC_NAME}"

echo "==== 核对关键字段 ===="
cat "${SVC_PATH}" | grep -E '^(WorkingDirectory|ExecStart|User|Group|EnvironmentFile|Restart)=' || true

echo "==== 确认 /usr/bin/python3 指向 ===="
readlink -f /usr/bin/python3 || true

echo "==== 确认 app.py 存在 ===="
cat "$(systemctl cat ${SVC_NAME} | grep WorkingDirectory= | cut -d'=' -f2)/app.py" | head -n 1 || true

echo "==== 服务状态 ===="
systemctl is-enabled "${SVC_NAME}" || true
systemctl is-active "${SVC_NAME}" || true
systemctl status "${SVC_NAME}" --no-pager -l || true

echo "==== 最近50行日志 ===="
journalctl -u "${SVC_NAME}" -n 50 --no-pager || true

# 可选：检查常见端口是否被占用（按需修改端口列表）
echo "==== 端口占用（示例：5000/8000/16003）===="
ss -lntp | grep -E ':(5000|8000|16003)\b' || true
BASH

chmod +x check_wake_service.sh
