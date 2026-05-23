#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")


apt install ufw curl sudo -y

sudo ufw allow 22
sudo ufw allow 3000:65535/tcp
sudo ufw allow 3000:65535/udp

echo "y" | sudo ufw enable

sudo ufw status

curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/ssh_permissions.sh | sudo bash

history -c

# 自我删除
history -c
rm -- "$SCRIPT_PATH"