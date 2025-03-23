from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import csv

# 设置无头浏览器
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")

# 创建浏览器对象（确保本地已安装 chromedriver 并在 PATH 中）
driver = webdriver.Chrome(options=options)

# 打开页面
url = "https://www.serverroom.net/dedicated/instant/"
driver.get(url)

# 给 JavaScript 时间加载
time.sleep(5)

# 获取页面源码
html = driver.page_source
driver.quit()

# 解析 HTML
soup = BeautifulSoup(html, "html.parser")

# 获取所有包含折扣信息的服务器条目
servers = soup.find_all("div", class_="server-card")

data = []

for server in servers:
    discount_tag = server.find("p", class_="discount-tag")
    if discount_tag:
        title = server.find("p", class_="title").text.strip()
        specs = server.find("div", class_="server-specs").text.strip()
        location = server.find("div", class_="server-location").text.strip()
        price = server.find("div", class_="server-info").text.strip().split("\n")[0]
        discount = discount_tag.text.strip()

        data.append([title, specs, location, price, discount])

# 写入 CSV 文件
with open("discount_servers.csv", mode="w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Server Title", "Specs", "Location", "Price", "Discount"])
    writer.writerows(data)

print("爬取完成，已保存为 discount_servers.csv")
