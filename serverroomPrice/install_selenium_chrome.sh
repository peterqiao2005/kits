#!/bin/bash
set -e

echo "[+] 更新系统..."
sudo apt update -y
sudo apt install -y wget unzip curl gnupg python3 python3-pip \
    libxi6 libgconf-2-4 libnss3 libasound2 libatk1.0-0 \
    libatk-bridge2.0-0 libcups2 libxkbcommon0 fonts-liberation

echo "[+] 安装 Google Chrome..."
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/chrome.deb
sudo apt install -y /tmp/chrome.deb
rm -f /tmp/chrome.deb

CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d. -f1)
echo "[+] 检测到 Chrome 主版本: $CHROME_VERSION"

echo "[+] 下载匹配的 ChromeDriver..."
wget -q https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}.0.0/linux64/chromedriver-linux64.zip -O /tmp/chromedriver.zip
unzip -q /tmp/chromedriver.zip -d /tmp/
sudo mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver
rm -rf /tmp/chromedriver*

echo "[+] 安装 Python 库..."
pip3 install --upgrade pip
pip3 install selenium

echo "[+] 安装完成，测试运行中..."
python3 - <<'EOF'
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)
driver.get("https://www.python.org")
print("[TEST] Title:", driver.title)
driver.quit()
EOF

echo "[+] 安装和测试完成！"
