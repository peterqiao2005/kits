#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")

apt-get update

apt install ufw curl sudo -y

sudo ufw allow 22
sudo ufw allow 3000:65535/tcp
sudo ufw allow 3000:65535/udp

echo "y" | sudo ufw enable

sudo ufw status

curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/ssh_permissions.sh | sudo bash

nvidia-smi -pm 1

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update

sudo apt install -y nvidia-container-runtime nvidia-container-toolkit
sudo apt install -y nvidia-docker2

curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/install_docker.sh -o install_docker.sh && chmod +x install_docker.sh && ./install_docker.sh

echo '{
  "default-runtime": "nvidia",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}' | sudo tee /etc/docker/daemon.json > /dev/null
	
systemctl restart docker

# 自我删除
rm -- "$SCRIPT_PATH"