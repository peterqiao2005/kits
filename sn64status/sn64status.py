from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import pandas as pd
import time

# 配置无头浏览器（可省略无头）
chrome_options = Options()
#chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")

# 启动浏览器
driver = webdriver.Chrome(options=chrome_options)
driver.get("https://chutes.ai/app/research/my-miner?hotkey=5CaqyHE9eBPyN469MNKor8R3zoyNsQwCzMZjd51xAR66S8tF")

# 等待页面加载完
time.sleep(10)  # 可根据网速调整

# 获取表格行
table_xpath = "/html/body/div/main/main/section[2]/section[1]/section/section[2]/div[14]/div/table"
rows = driver.find_elements(By.XPATH, table_xpath + "/tbody/tr")

data = []
for row in rows:
    cols = row.find_elements(By.TAG_NAME, "td")
    if len(cols) >= 4:
        gpu = cols[0].text.strip()
        chute = cols[1].text.strip()
        instance_id = cols[2].text.strip()
        verified = "✔" in cols[3].text or "✓" in cols[3].text
        data.append({
            "GPU": gpu,
            "Chute": chute,
            "Instance ID": instance_id,
            "Verified": verified
        })

driver.quit()

# 转为 DataFrame 并保存
df = pd.DataFrame(data)
df.to_excel("chutes_data.xlsx", index=False)
print("✅ 数据保存成功: chutes_data.xlsx")
