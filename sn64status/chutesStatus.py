import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 配置无头浏览器（可省略无头）
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")

# 启动浏览器 - 修复1：正确传递options参数
original_url = "https://chutes.ai/app/research/leaderboard"
driver = webdriver.Chrome(options=chrome_options)
driver.get(original_url)

# 等待表格加载完成（根据实际情况调整等待时间或条件）
table_xpath = "/html/body/div/main/main/section[2]/div[1]/main/div/div[2]/div/div/table"
WebDriverWait(driver, 30).until(
    EC.presence_of_element_located((By.XPATH, table_xpath))
)

# 获取表格行
rows = driver.find_elements(By.XPATH, table_xpath + "/tbody/tr")

data = []
hotkey_urls = []
for row in rows:
    cols = row.find_elements(By.TAG_NAME, "td")
    if len(cols) >= 7:
        # 修复2：使用get_attribute('textContent')替代.text
        Rank = cols[0].get_attribute('textContent').strip()
        Final_Score = cols[2].get_attribute('textContent').strip()
        hotkey_urls.append((cols[1].find_element(By.TAG_NAME, "a").get_attribute("href")))
        data.append({
            "Rank": Rank,
            "Final Score": Final_Score
        })

for i, url in enumerate(hotkey_urls):
    driver.get(url)
    # 等待详情页面加载
    sub_table_xpath = "/html/body/div/main/main/section[2]/div[1]/main/div/div[14]/div/table"
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, sub_table_xpath))
    )

    # 提取详情信息（根据实际页面调整）- 修复2：使用get_attribute('textContent')
    hotkey = driver.find_element(By.XPATH, "/html/body/div/main/main/section[2]/div[1]/main/div/h5[1]").get_attribute('textContent').strip()

    RAW_Bounty_Count = driver.find_element(By.XPATH, "/html/body/div/main/main/section[2]/div[1]/main/div/div[5]/div[1]/h6").get_attribute('textContent').strip()
    RAW_Compute_Units = driver.find_element(By.XPATH, "/html/body/div/main/main/section[2]/div[1]/main/div/div[5]/div[2]/h6").get_attribute('textContent').strip()
    RAW_Invocation_Count = driver.find_element(By.XPATH, "/html/body/div/main/main/section[2]/div[1]/main/div/div[5]/div[3]/h6").get_attribute('textContent').strip()
    RAW_Unique_Chute_Count = driver.find_element(By.XPATH, "/html/body/div/main/main/section[2]/div[1]/main/div/div[5]/div[4]/h6").get_attribute('textContent').strip()

    NORMALIZED_Bounty_Count = driver.find_element(By.XPATH, "/html/body/div/main/main/section[2]/div[1]/main/div/div[5]/div[5]/h6").get_attribute('textContent').strip()
    NORMALIZED_Compute_Units = driver.find_element(By.XPATH, "/html/body/div/main/main/section[2]/div[1]/main/div/div[5]/div[6]/h6").get_attribute('textContent').strip()
    NORMALIZED_Invocation_Count = driver.find_element(By.XPATH, "/html/body/div/main/main/section[2]/div[1]/main/div/div[5]/div[7]/h6").get_attribute('textContent').strip()
    NORMALIZED_Unique_Chute_Count = driver.find_element(By.XPATH, "/html/body/div/main/main/section[2]/div[1]/main/div/div[5]/div[8]/h6").get_attribute('textContent').strip()

    GPU_xpath = "/html/body/div/main/main/section[2]/div[1]/main/div/div[9]/div[1]/div/div[1]"
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.XPATH, GPU_xpath))
    )

    GPU_elements = driver.find_elements("xpath",
    "/html/body/div/main/main/section[2]/div[1]/main/div/div[9]/div[1]/div/div[1]/div/div[./p]/p"
    )

    if len(GPU_elements) == 1:
        # 只有一个子元素，获取其文本 - 修复2：使用get_attribute('textContent')
        GPU_list = GPU_elements[0].get_attribute('textContent').strip()
    else:
        # 多个子元素，组合所有文本 - 修复2：使用get_attribute('textContent')
        texts = [elem.get_attribute('textContent').strip() for elem in GPU_elements]
        GPU_list = " ".join(texts)

    sub_data = []
    rows = driver.find_elements(By.XPATH, sub_table_xpath + "/tbody/tr")
    for row in rows:
        cols = row.find_elements(By.TAG_NAME, "td")
        if len(cols) >= 4:
            # 修复2：使用get_attribute('textContent')替代.text
            gpu = cols[0].get_attribute('textContent').strip()
            chute = cols[1].get_attribute('textContent').strip().replace('\n', ' ')
            instance_id = cols[2].get_attribute('textContent').strip()
            verified_text = cols[3].get_attribute('textContent')
            verified = "✔" in verified_text or "✓" in verified_text
            sub_data.append({
                "GPU": gpu,
                "Chute": chute,
                "Instance ID": instance_id,
                "Verified": verified
            })
    data[i]["Hotkey"] = hotkey
    data[i]["RAW"] = {
        "Bounty Count": RAW_Bounty_Count,
        "Compute Units": RAW_Compute_Units,
        "Invocation Count": RAW_Invocation_Count,
        "Unique Chute Count": RAW_Unique_Chute_Count
    }
    data[i]["NORMALIZED"] = {
        "Bounty Count": NORMALIZED_Bounty_Count,
        "Compute Units": NORMALIZED_Compute_Units,
        "Invocation Count": NORMALIZED_Invocation_Count,
        "Unique Chute Count": NORMALIZED_Unique_Chute_Count
    }
    data[i]["GPU_list"] = GPU_list
    data[i]["GPU_Info"] = sub_data

driver.quit()

def export_to_excel(data, filename=None):
    """
    将数据导出到Excel文件,包含两个工作表:
    1. 矿工主数据（每个矿工一行）
    2. GPU详细信息(每个GPU实例一行)
    """
    # 如果没有提供文件名，使用带时间戳的默认文件名
    if filename is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chutes_data_{timestamp}.xlsx"

    # 创建主数据DataFrame
    main_data = []
    for item in data:
        # 创建主记录
        main_record = {
            "Rank": item.get("Rank", ""),
            "Hotkey": item.get("Hotkey", ""),
            "Final Score": item.get("Final Score", ""),
            "GPU_list": item.get("GPU_list", "")
        }

        # 添加RAW数据
        raw = item.get("RAW", {})
        for key, value in raw.items():
            main_record[f"RAW_{key}"] = value

        # 添加NORMALIZED数据
        normalized = item.get("NORMALIZED", {})
        for key, value in normalized.items():
            main_record[f"NORMALIZED_{key}"] = value

        main_data.append(main_record)

    # 创建主数据DataFrame
    df_main = pd.DataFrame(main_data)

    # 创建GPU详细信息DataFrame
    gpu_data = []
    for item in data:
        hotkey = item.get("Hotkey", "")
        gpu_info = item.get("GPU_Info", [])

        for gpu in gpu_info:
            gpu_record = {
                "Hotkey": hotkey,  # 关联键
                "GPU": gpu.get("GPU", ""),
                "Chute": gpu.get("Chute", ""),
                "Instance ID": gpu.get("Instance ID", ""),
                "Verified": gpu.get("Verified", False)
            }
            gpu_data.append(gpu_record)

    df_gpu = pd.DataFrame(gpu_data)

    # 创建Excel写入器
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # 写入主数据工作表
        df_main.to_excel(
            writer,
            sheet_name="矿工数据",
            index=False
        )

        # 写入GPU详细信息工作表
        df_gpu.to_excel(
            writer,
            sheet_name="GPU信息",
            index=False
        )

        # 添加时间戳元数据工作表
        metadata = {
            "报告生成时间": [datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
            "矿工记录数": [len(df_main)],
            "GPU记录数": [len(df_gpu)]
        }
        df_meta = pd.DataFrame(metadata)
        df_meta.to_excel(
            writer,
            sheet_name="元数据",
            index=False
        )

        # 获取工作表对象进行格式设置
        main_sheet = writer.sheets["矿工数据"]
        gpu_sheet = writer.sheets["GPU信息"]
        meta_sheet = writer.sheets["元数据"]

        # 设置列宽（可选）
        for sheet in [main_sheet, gpu_sheet, meta_sheet]:
            for column in sheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2) * 1.2
                sheet.column_dimensions[column_letter].width = adjusted_width

        # 冻结标题行（可选）
        main_sheet.freeze_panes = "A2"
        gpu_sheet.freeze_panes = "A2"
        meta_sheet.freeze_panes = "A2"

    print(f"Excel文件已创建: {filename}")
    print(f"主工作表包含 {len(df_main)} 条矿工记录")
    print(f"GPU工作表包含 {len(df_gpu)} 条GPU记录")
    print(f"报告生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# 使用函数
export_to_excel(data)

print(f"成功收集了 {len(data)} 条记录")
