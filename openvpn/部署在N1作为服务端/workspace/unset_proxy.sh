#!/bin/bash
# 清除所有代理配置

echo "清除环境变量代理..."
sed -i '/# === Proxy Settings Start ===/,/# === Proxy Settings End ===/d' ~/.bashrc

echo "清除 apt 代理..."
sudo rm -f /etc/apt/apt.conf.d/99proxy

echo "清除 git 代理..."
git config --global --unset http.proxy
git config --global --unset https.proxy

echo "清除 wget 代理..."
rm -f ~/.wgetrc

echo "代理已取消。建议运行 'source ~/.bashrc' 以使当前终端生效。"

