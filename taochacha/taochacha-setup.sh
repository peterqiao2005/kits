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

# 检查 pm2 是否已安装
if ! command -v pm2 &> /dev/null
then
    echo "pm2 未安装，正在安装..."
    # 更新包索引
    sudo apt update
    # 安装 Node.js 和 npm（如果未安装）
    if ! command -v node &> /dev/null || ! command -v npm &> /dev/null
    then
        echo "Node.js 和 npm 未安装，正在安装..."
        sudo apt install -y nodejs npm
    fi
    # 安装 pm2
    sudo npm install -g pm2@5.4.3
    echo "pm2 安装完成。"
    pm2 install pm2-logrotate
    pm2 set pm2-logrotate:max_size 100M
    pm2 set pm2-logrotate:retain 5
    pm2 set pm2-logrotate:compress true
    echo "已安装pm2-logrotate，并配置单个log最大为100M。"
else
    echo "pm2 已安装，无需操作。"
    pm2 install pm2-logrotate
    pm2 set pm2-logrotate:max_size 100M
    pm2 set pm2-logrotate:retain 5
    pm2 set pm2-logrotate:compress true
    echo "已安装pm2-logrotate，并配置单个log最大为100M。"
fi

mkdir -p ~/workspace/taochacha/
cd ~/workspace/taochacha/

yes "" | sudo add-apt-repository ppa:deadsnakes/ppa
# sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev
sudo apt install -y python3-pip
python3.10 -m venv machine_api
source machine_api/bin/activate
pip install fastapi
pip install uvicorn

curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/taochacha/docker-compose.yml -o docker-compose.yml
docker compose up -d

curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/taochacha/machine_api.py -o machine_api.py
pm2 start machine_api.py --interpreter python3
deactivate

cd ~
history -c

# 自我删除
rm -- "$SCRIPT_PATH"
