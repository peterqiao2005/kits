#!/bin/bash

# 部署目录
BASE_DIR="/opt/monitoring"

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

# 安装 Grafana
echo "Installing Grafana..."
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
sudo add-apt-repository "deb https://packages.grafana.com/oss/deb stable main"
sudo apt-get update
sudo apt-get install -y grafana

# 启动 Grafana 使用 PM2 并设置监听端口 3001
pm2 start /usr/sbin/grafana-server --name grafana -- \
  --config=/etc/grafana/grafana.ini \
  --homepath=/usr/share/grafana \
  --http.port=3001

# 设置 PM2 开机自启动
pm2 save
pm2 startup

# 提示用户
echo "Deployment complete!"
echo "Prometheus is running on port 3002"
echo "Grafana is running on port 3001"
