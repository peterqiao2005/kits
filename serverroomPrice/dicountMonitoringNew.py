#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 https://www.serverroom.net/dedicated/instant/ 抓取折扣 ≥ 25 % 的服务器信息，
并追加写入 high_discount_servers.csv

新增字段:
    - Storage
    - Bandwidth
    - Initial Price
    - Final Price
"""
import re
import csv
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

# ========= ✅ 配置 =========
DISCOUNT_THRESHOLD = -25.0                     # 折扣阈值（含等于）
CSV_FILE = "high_discount_servers.csv"
URL = "https://www.serverroom.net/dedicated/instant/"
WAIT_SEC = 5                                   # JS 加载等待秒数
# ==========================

timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")

# ---- 启动 headless Chrome ----
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=options)
driver.get(URL)
time.sleep(WAIT_SEC)           # 等待页面完全渲染
html = driver.page_source
driver.quit()

# ---- 解析 HTML ----
soup = BeautifulSoup(html, "html.parser")
servers = soup.find_all("div", class_="server-card")

filtered_rows = []

for srv in servers:
    tag = srv.find("p", class_="discount-tag")
    if not tag:
        continue

    # 折扣值
    try:
        discount_val = float(tag.text.strip().replace("%", ""))
    except ValueError:
        continue

    if discount_val > DISCOUNT_THRESHOLD:      # 仅保留打折幅度 ≥ 阈值的
        continue

    # -------- 基本信息 --------
    title = srv.find("p", class_="title").text.strip()

    # 逐条读取规格，转为 dict，方便按 key 取值
    spec_dict = {}
    for spec in srv.find_all("div", class_="server-spec"):
        key = spec.find("p", class_="feature-key").text.strip()
        val = spec.find("p", class_="feature-value").text.strip()
        spec_dict[key] = val

    memory     = spec_dict.get("Memory", "")
    storage    = spec_dict.get("Storage", "")
    bandwidth  = spec_dict.get("Bandwidth", "")
    os_        = spec_dict.get("OS", "")

    location   = srv.find("div", class_="server-location").text.strip()

    # -------- 价格 --------
    def _num(txt: str) -> str:
        """提取数字（保留逗号和小数点）"""
        m = re.search(r"[\d\.,]+", txt)
        return m.group().replace(",", "") if m else "N/A"

    initial_tag = srv.select_one(".initial-price del")
    final_tag   = srv.select_one(".final-price")

    initial_price = _num(initial_tag.text) if initial_tag else "N/A"
    final_price   = _num(final_tag.text)   if final_tag   else "N/A"

    filtered_rows.append([
        title,
        memory,
        storage,
        bandwidth,
        os_,
        location,
        initial_price,
        final_price,
        f"{discount_val}%",
        timestamp
    ])

# ---- 写 CSV（追加）----
header = [
    "Server Title", "Memory", "Storage", "Bandwidth", "OS",
    "Location", "Initial Price", "Final Price", "Discount", "Timestamp"
]

with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    if f.tell() == 0:
        writer.writerow(header)
    writer.writerows(filtered_rows)

print(f"[完成] 共记录 {len(filtered_rows)} 条数据，已追加至 {CSV_FILE}")
