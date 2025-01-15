#!/bin/bash

# 部署目录
BASE_DIR="/opt/monitoring"

# 确保PM2安装
if ! command -v pm2 &> /dev/null; then
  echo "安装PM2..."
  npm install -g pm2
fi

# Prometheus 和 Grafana 版本
PROMETHEUS_VERSION="2.48.0"

# 创建目录
mkdir -p $BASE_DIR

# 安装 Prometheus
echo "Installing Prometheus..."
cd $BASE_DIR
wget https://github.com/prometheus/prometheus/releases/download/v${PROMETHEUS_VERSION}/prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz
tar -xvzf prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz
mv prometheus-${PROMETHEUS_VERSION}.linux-amd64 prometheus
rm prometheus-${PROMETHEUS_VERSION}.linux-amd64.tar.gz

# 配置 Prometheus
cat <<EOF > $BASE_DIR/prometheus/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'node_exporters'
    static_configs:
      - targets: ['192.168.1.101:3003', '192.168.1.102:3003', '192.168.1.103:3003']
EOF

# 启动 Prometheus 使用 PM2 并设置监听端口 3002
pm2 start $BASE_DIR/prometheus/prometheus --name prometheus -- \
  --config.file=$BASE_DIR/prometheus/prometheus.yml \
  --storage.tsdb.path=$BASE_DIR/prometheus/data \
  --web.listen-address="0.0.0.0:3002"

# 检查是否以root用户运行
if [ "$EUID" -ne 0 ]; then
  echo "请以root权限运行此脚本。"
  exit 1
fi

# 安装必要的依赖
apt update
apt install -y curl software-properties-common

# 添加Grafana的官方仓库并安装Grafana
if ! grep -q "grafana" /etc/apt/sources.list.d/grafana.list 2>/dev/null; then
  echo "添加Grafana官方仓库..."
  echo "deb https://packages.grafana.com/oss/deb stable main" | tee /etc/apt/sources.list.d/grafana.list
  curl -fsSL https://packages.grafana.com/gpg.key | gpg --dearmor -o /usr/share/keyrings/grafana-archive-keyring.gpg
fi

apt update
apt install -y grafana

# 配置Grafana端口
GRAFANA_PORT=3001
GRAFANA_CONFIG="/etc/grafana/grafana.ini"
echo "配置Grafana监听端口为$GRAFANA_PORT..."
sed -i "s/^;\\?http_port = .*/http_port = $GRAFANA_PORT/" "$GRAFANA_CONFIG"

# 确保PM2安装
if ! command -v pm2 &> /dev/null; then
  echo "安装PM2..."
  npm install -g pm2
fi

# 使用PM2管理Grafana
PM2_APP_NAME="grafana"
echo "删除旧的PM2任务（如果存在）..."
pm2 delete "$PM2_APP_NAME" 2>/dev/null || true

# 启动并保存新的PM2任务
pm2 start /usr/sbin/grafana-server --name "$PM2_APP_NAME" -- \
  --config=/etc/grafana/grafana.ini \
  --homepath=/usr/share/grafana

pm2 save

# 启动PM2开机自启
echo "配置PM2开机自启..."
eval "$(pm2 startup | tail -n +2)"

# 打印Grafana服务状态和访问提示
echo "Grafana服务已启动。"
echo "访问地址: http://<服务器IP>:$GRAFANA_PORT"