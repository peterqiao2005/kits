cat > deploy_wake_service.sh <<'BASH'
#!/usr/bin/env bash
set -euo pipefail

# === 基本参数（自动探测，不需要手工改） ===
WORKDIR="$(pwd)"
RUNUSER="$(id -un)"
RUNGROUP="$(id -gn)"
SVC_NAME="wake.service"
SVC_PATH="/etc/systemd/system/${SVC_NAME}"

# === 先做几项必要检查 ===
# 1) app.py 必须在当前目录
if [ ! -f "${WORKDIR}/app.py" ]; then
  echo "ERROR: ${WORKDIR}/app.py 不存在。请在 app.py 所在目录执行本脚本。"
  exit 1
fi

# 2) /usr/bin/python3 必须存在
if [ ! -x /usr/bin/python3 ]; then
  echo "ERROR: /usr/bin/python3 不存在或不可执行。"
  exit 1
fi

# 3) 可选 .env（不会强制要求）
ENV_FILE="${WORKDIR}/.env"
[ -f "${ENV_FILE}" ] && echo "发现 .env，将以 EnvironmentFile 方式加载。"

# === 生成 systemd 单元（固定 ExecStart=/usr/bin/python3） ===
TMP_UNIT="$(mktemp)"
cat > "${TMP_UNIT}" <<EOF
[Unit]
Description=Wake-on-LAN Web Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${WORKDIR}
# 固定为 /usr/bin/python3，按你的要求
ExecStart=/usr/bin/python3 ${WORKDIR}/app.py
User=${RUNUSER}
Group=${RUNGROUP}
Restart=always
RestartSec=2
Environment=PYTHONUNBUFFERED=1
# 若存在 .env 则加载（可选）
EnvironmentFile=-${ENV_FILE}
# 提高文件描述符/内核资源限制（可选，按需）
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

# 写入 /etc/systemd/system
sudo mv "${TMP_UNIT}" "${SVC_PATH}"
sudo chown root:root "${SVC_PATH}"
sudo chmod 0644 "${SVC_PATH}"

# 让 systemd 识别
sudo systemctl daemon-reload

# 启用并启动
sudo systemctl enable --now "${SVC_NAME}"

# === 自检（按你习惯用 grep）===
echo "==== 核对关键字段 ===="
cat "${SVC_PATH}" | grep -E '^(WorkingDirectory|ExecStart|User|Group|EnvironmentFile|Restart)=' || true

echo "==== 查看状态 ===="
systemctl status "${SVC_NAME}" --no-pager -l || true

echo "==== 最近50行日志 ===="
journalctl -u "${SVC_NAME}" -n 50 --no-pager || true

echo "部署完成。若后续修改 service，请执行：sudo systemctl daemon-reload && sudo systemctl restart ${SVC_NAME}"
BASH

chmod +x deploy_wake_service.sh
