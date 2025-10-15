#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 https://www.serverroom.net/dedicated/instant/ 抓取折扣 ≥ 25 % 的服务器信息，
并追加写入 high_discount_servers.csv，同时写入 PostgreSQL 数据库。

新增字段:
    - Storage
    - Bandwidth
    - Initial Price
    - Final Price
"""

import re
import csv
import time
import os
import sys
import traceback
import psycopg2
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

DB_CONFIG = {
    "dbname": "metagraph",
    "user": "tao",
    "password": "umobile$prabayar",
    "host": "127.0.0.1",
    "port": "5432"
}

TABLE_NAME = "high_discount_servers"
# ==========================


def init_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def parse_page(html, timestamp):
    """解析页面，返回符合条件的行数据"""
    soup = BeautifulSoup(html, "html.parser")
    servers = soup.find_all("div", class_="server-card")

    rows = []

    for srv in servers:
        tag = srv.find("p", class_="discount-tag")
        if not tag:
            continue

        # 折扣值
        try:
            discount_val = float(tag.text.strip().replace("%", ""))
        except ValueError:
            continue

        if discount_val > DISCOUNT_THRESHOLD:  # 仅保留打折幅度 ≥ 阈值的
            continue

        # -------- 基本信息 --------
        title = srv.find("p", class_="title").text.strip()

        # 逐条读取规格，转为 dict
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
            m = re.search(r"[\d\.,]+", txt)
            return m.group().replace(",", "") if m else "N/A"

        initial_tag = srv.select_one(".initial-price del")
        final_tag   = srv.select_one(".final-price")

        initial_price = _num(initial_tag.text) if initial_tag else "N/A"
        final_price   = _num(final_tag.text)   if final_tag   else "N/A"

        rows.append([
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

    return rows


def write_csv(rows):
    """写入 CSV"""
    header = [
        "Server Title", "Memory", "Storage", "Bandwidth", "OS",
        "Location", "Initial Price", "Final Price", "Discount", "Timestamp"
    ]

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if f.tell() == 0:
            writer.writerow(header)
        writer.writerows(rows)


def write_db(rows):
    """写入 PostgreSQL"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            server_title TEXT,
            memory TEXT,
            storage TEXT,
            bandwidth TEXT,
            os TEXT,
            location TEXT,
            initial_price TEXT,
            final_price TEXT,
            discount TEXT,
            timestamp TEXT
        )
    """)

    insert_sql = f"""
        INSERT INTO {TABLE_NAME} 
        (server_title, memory, storage, bandwidth, os, location, initial_price, final_price, discount, timestamp)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """

    cursor.executemany(insert_sql, rows)
    conn.commit()
    cursor.close()
    conn.close()


def main():
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")

    driver = init_driver()
    driver.get(URL)
    time.sleep(WAIT_SEC)
    html = driver.page_source
    driver.quit()

    rows = parse_page(html, timestamp)

    if rows:
        write_csv(rows)
        write_db(rows)
        print(f"[完成] 共记录 {len(rows)} 条数据，已写入 CSV 和数据库。")
    else:
        print("[提示] 没有符合条件的记录。")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("❌ 程序异常退出：")
        traceback.print_exc()
        if os.name == "nt":  # Windows 上防止闪退
            input("按回车键退出...")
        sys.exit(1)
