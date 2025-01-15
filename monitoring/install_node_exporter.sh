#!/bin/bash

# 部署目录
BASE_DIR="/opt/node_exporter"

# Node Exporter 版本
NODE_EXPORTER_VERSION="1.6.0"

# 检查是否有旧的 Node Exporter 运行
pm2 delete node_exporter &>/dev/null

# 安装 Node Exporter
echo "Installing Node Exporter..."
mkdir -p $BASE_DIR
cd $BASE_DIR
wget https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
tar -xvzf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
mv node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64/* .
rm -rf node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64 node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz

# 启动 Node Exporter 使用 PM2 并设置监听端口 3003
pm2 start $BASE_DIR/node_exporter --name node_exporter -- \
  --web.listen-address="0.0.0.0:3003"

# 设置 PM2 开机自启动
pm2 save
pm2 startup

echo "Node Exporter has been installed and is running on port 3003"
