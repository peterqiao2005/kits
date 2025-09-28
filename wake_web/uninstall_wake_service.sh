cat > uninstall_wake_service.sh <<'BASH'
#!/usr/bin/env bash
set -euo pipefail
SVC_NAME="wake.service"
SVC_PATH="/etc/systemd/system/${SVC_NAME}"

sudo systemctl disable --now "${SVC_NAME}" || true
sudo rm -f "${SVC_PATH}"
sudo systemctl daemon-reload
echo "已卸载 ${SVC_NAME}"
BASH

chmod +x uninstall_wake_service.sh
