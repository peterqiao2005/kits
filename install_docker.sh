#!/bin/bash

# 安装 Docker 和 Docker Compose 的一键脚本

echo "更新包索引..."
sudo apt-get update

echo "安装必要的包..."
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common

echo "添加 Docker 的官方 GPG 密钥..."
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

echo "设置 Docker 稳定版的存储库..."
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "更新包索引..."
sudo apt-get update

echo "安装 Docker..."
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

echo "启动 Docker 并设置开机自启..."
sudo systemctl start docker
sudo systemctl enable docker

echo "验证 Docker 安装..."
sudo docker --version

echo "下载 Docker Compose..."
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

echo "赋予 Docker Compose 可执行权限..."
sudo chmod +x /usr/local/bin/docker-compose
	
systemctl restart docker

echo "验证 Docker Compose 安装..."
docker-compose --version

echo "Docker 和 Docker Compose 安装完成！"
