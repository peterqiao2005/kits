#!/bin/bash
set -e

echo "== 1) 清理当前 shell 代理环境变量（仅对本次执行的 shell 有效） =="
unset http_proxy https_proxy ftp_proxy HTTP_PROXY HTTPS_PROXY FTP_PROXY ALL_PROXY all_proxy

echo "== 2) 从 ~/.bashrc 删除 Proxy Settings 区块 =="
if [ -f ~/.bashrc ]; then
  sed -i '/# === Proxy Settings Start ===/,/# === Proxy Settings End ===/d' ~/.bashrc
fi

echo "== 3) 清理 apt 代理 =="
rm -f /etc/apt/apt.conf.d/99proxy

echo "== 4) 清理 git 代理 =="
git config --global --unset http.proxy 2>/dev/null || true
git config --global --unset https.proxy 2>/dev/null || true

echo "== 5) 清理 wget 代理 =="
rm -f ~/.wgetrc

echo "== 6) 清理 Docker daemon 代理 =="
rm -f /etc/systemd/system/docker.service.d/http-proxy.conf
rm -f /etc/systemd/system/docker.service.d/proxy.conf
systemctl daemon-reload
systemctl restart docker

echo
echo "== 验证：当前 shell 代理变量（应只剩 no_proxy 或空）=="
env | grep -iE '^(http_proxy|https_proxy|ftp_proxy|HTTP_PROXY|HTTPS_PROXY|FTP_PROXY|ALL_PROXY|all_proxy|no_proxy)=' || true

echo
echo "== 验证：apt 代理（应无输出）=="
ls -l /etc/apt/apt.conf.d/99proxy 2>/dev/null || true

echo
echo "== 验证：git 代理（应无输出）=="
git config --global --get http.proxy 2>/dev/null || true
git config --global --get https.proxy 2>/dev/null || true

echo
echo "== 验证：Docker daemon 环境（应无 HTTP_PROXY/HTTPS_PROXY）=="
systemctl show docker --property=Environment | cat

echo
echo "提示：如果你想让“当前终端”也立刻生效，请在当前终端执行："
echo "  unset http_proxy https_proxy ftp_proxy HTTP_PROXY HTTPS_PROXY FTP_PROXY ALL_PROXY all_proxy"
echo "然后再执行："
echo "  source ~/.bashrc"
