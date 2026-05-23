#!/bin/bash
sudo snap remove microk8s --purge
sudo rm -rf /var/snap/microk8s
sudo rm -rf ~/snap/microk8s
sudo rm -rf /etc/microk8s
sudo rm -rf /data/snap/cache/

echo "🚀 开始修复 Docker 服务..."
sudo systemctl stop docker
sudo systemctl stop containerd
sudo systemctl disable docker
sudo systemctl disable containerd


# 移除 Docker 相关包
sudo apt-get remove --purge -y docker.io docker-ce docker-ce-cli containerd.io runc docker-compose-plugin
sudo apt-get autoremove -y
sudo apt-get autoclean

# 删除 Docker 残留数据
sudo rm -rf /var/lib/docker
sudo rm -rf /var/lib/containerd
sudo rm -rf /etc/docker
sudo rm -rf /var/run/docker.sock

sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable docker
sudo systemctl start docker

sudo systemctl unmask docker
sudo systemctl unmask containerd
sudo systemctl restart containerd
sudo systemctl restart docker

# 1️⃣ 终止所有 Docker 相关进程
sudo pkill -9 dockerd
sudo pkill -9 containerd

# 2️⃣ 重新启动 containerd（Docker 依赖它）
sudo systemctl restart containerd

# 3️⃣ 确保 Docker 服务未被屏蔽
sudo systemctl unmask docker
sudo systemctl unmask containerd

# 4️⃣ 启动 Docker
sudo systemctl start docker
sudo systemctl enable docker

# 5️⃣ 检查是否创建了 /var/run/docker.sock
ls -l /var/run/docker.sock


# 4️⃣ 检查 Docker 状态
echo "🔍 检查 Docker 状态..."
sudo systemctl status docker --no-pager

# 5️⃣ 测试 Docker 是否正常运行
echo "🛠️ 运行 Docker 测试..."
docker info && docker ps

echo "🚀 Docker 修复完成！"
