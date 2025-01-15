#!/bin/bash

# 配置CPU使用高性能模式的一键脚本

echo "更新包索引..."
sudo apt-get update

echo "安装必要的包..."
sudo apt install -y linux-tools-common linux-tools-$(uname -r)

echo "设置CPU为高性能模式..."
cpupower frequency-info

echo "检查CPU状态..."
cat /proc/cpuinfo | grep "MHz"
