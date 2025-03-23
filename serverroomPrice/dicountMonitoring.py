import re
import csv
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

# ========== ✅ 配置项 ==========
DISCOUNT_THRESHOLD = -25.0  # 最低折扣过滤阈值（含等于）
CSV_FILE = "high_discount_servers.csv"
# ==============================

# 获取当前时间（北京时间 UTC+8）
timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")

# 启动 headless Chrome
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
driver = webdriver.Chrome(options=options)

driver.get("https://www.serverroom.net/dedicated/instant/")
time.sleep(5)  # 等待 JavaScript 加载完毕
html = driver.page_source
driver.quit()

# 解析 HTML
soup = BeautifulSoup(html, "html.parser")
servers = soup.find_all("div", class_="server-card")

filtered_data = []

for server in servers:
    discount_tag = server.find("p", class_="discount-tag")
    if discount_tag:
        try:
            discount_str = discount_tag.text.strip().replace("%", "")
            discount_val = float(discount_str)
        except:
            continue

        if discount_val <= DISCOUNT_THRESHOLD:
            # 获取基本信息
            title = server.find("p", class_="title").text.strip()
            specs = server.find("div", class_="server-specs").text.strip()
            location = server.find("div", class_="server-location").text.strip()

            # 解析价格字段，过滤乱码
            try:
                raw_price = server.find("div", class_="server-info").text.strip().split("\n")[0]
                price_match = re.search(r"[\d\.,]+", raw_price)
                price = price_match.group() if price_match else "N/A"
            except:
                price = "N/A"

            filtered_data.append([title, specs, location, price, f"{discount_val}%", timestamp])

# 写入（追加）CSV 文件
with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    if f.tell() == 0:
        writer.writerow(["Server Title", "Specs", "Location", "Price", "Discount", "Timestamp"])
    writer.writerows(filtered_data)

print(f"[完成] 共记录 {len(filtered_data)} 条符合条件的数据，已追加至 {CSV_FILE}")
