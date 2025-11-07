#!/bin/bash

# ⚠️ 用 HTTP 协议代替 HTTPS 协议（关键点）
PROXY_URL="http://share:32167share@192.168.1.218:10802"

echo "设置环境变量代理..."
export http_proxy="$PROXY_URL"
export https_proxy="$PROXY_URL"
export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"
export ftp_proxy="$PROXY_URL"
export no_proxy="localhost,127.0.0.1,::1"

# 写入 ~/.bashrc
grep -q "export http_proxy=" ~/.bashrc || cat <<EOF >> ~/.bashrc

# === Proxy Settings Start ===
export http_proxy="$PROXY_URL"
export https_proxy="$PROXY_URL"
export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"
export ftp_proxy="$PROXY_URL"
export no_proxy="localhost,127.0.0.1,::1"
# === Proxy Settings End ===
EOF

echo "配置 apt 代理..."
sudo mkdir -p /etc/apt/apt.conf.d
echo "Acquire::http::Proxy \"$PROXY_URL\";" | sudo tee /etc/apt/apt.conf.d/99proxy > /dev/null
echo "Acquire::https::Proxy \"$PROXY_URL\";" | sudo tee -a /etc/apt/apt.conf.d/99proxy > /dev/null

echo "配置 git 代理..."
git config --global http.proxy "$PROXY_URL"
git config --global https.proxy "$PROXY_URL"

echo "配置 wget 代理..."
echo "use_proxy = on" > ~/.wgetrc
echo "https_proxy = $PROXY_URL" >> ~/.wgetrc
echo "http_proxy = $PROXY_URL" >> ~/.wgetrc

echo "代理设置完成。建议运行 'source ~/.bashrc' 以使当前终端生效。"

