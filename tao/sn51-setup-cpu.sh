#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")

apt-get update

apt install ufw curl sudo -y

sudo ufw allow 22
sudo ufw allow 3000:30000/tcp
sudo ufw allow 33000:65535/tcp
sudo ufw allow 3000:65535/udp

echo "y" | sudo ufw enable

sudo ufw status

curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/ssh_permissions.sh | sudo bash

curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/install_docker.sh -o install_docker.sh && chmod +x install_docker.sh && ./install_docker.sh

# 兼容不同系统的 SSH 重启方式
if command -v systemctl &> /dev/null; then
    sudo systemctl restart sshd
elif command -v service &> /dev/null; then
    sudo service ssh restart
elif [ -f /etc/init.d/ssh ]; then
    sudo /etc/init.d/ssh restart
else
    echo "无法重启 SSH，请手动重启。" >&2
fi

# 自我删除
rm -- "$SCRIPT_PATH"
