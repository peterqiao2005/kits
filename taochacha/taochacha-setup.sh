#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")

# 检查 Docker 是否已安装
if ! command -v docker &> /dev/null; then
    echo "Docker 未安装，正在安装..."

    # 更新 apt 包索引
    sudo apt update

    # 安装必要的依赖包
    sudo apt install -y apt-transport-https ca-certificates curl software-properties-common

    # 添加 Docker 官方 GPG 密钥
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

    # 设置 Docker 仓库
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    # 更新 apt 包索引并安装 Docker
    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io

    # 启动并启用 Docker
    sudo systemctl start docker
    sudo systemctl enable docker

    echo "Docker 安装完成！"
else
    echo "Docker 已安装，版本信息如下："
    docker --version
fi

# 检查 Docker Compose 是否已安装
if ! command -v docker compose &> /dev/null; then
    echo "Docker Compose 未安装，正在安装..."

    # 下载 Docker Compose 最新版本
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

    # 赋予执行权限
    sudo chmod +x /usr/local/bin/docker-compose

    # 创建符号链接（某些系统可能需要）
    sudo ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose

    echo "Docker Compose 安装完成！"
else
    echo "Docker Compose 已安装，版本信息如下："
    docker-compose --version
fi

mkdir -p ~/workspace/taochacha/
cd ~/workspace/taochacha/
curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/taochacha/docker-compose.yml -o docker-compose.yml
docker compose up -d

cd ~
history -c

# 自我删除
rm -- "$SCRIPT_PATH"
