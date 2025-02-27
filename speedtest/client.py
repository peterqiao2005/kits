import requests
import time
import os
import datetime
from datetime import timezone
import socket

# 生成随机数据
data_4k = os.urandom(4 * 1024)  # 4KB
data_150k = os.urandom(150 * 1024)  # 150KB

# 测试类型映射
test_categories = {
    '1': {
        'description': '测试4K数据',
        'sub_tests': {
            '1': '1. 不含数据，仅测算请求到响应的时间差',
            '2': '2. 发送4K数据，接收4K回应',
            '3': '3. 发送4K数据，无回应',
            '4': '4. 发送不含数据，接收4K回应',
        },
        'data': data_4k
    },
    '2': {
        'description': '测试150K数据',
        'sub_tests': {
            '1': '1. 不含数据，仅测算请求到响应的时间差',
            '5': '5. 发送150K数据，接收150K回应',
            '6': '6. 发送150K数据，无回应',
            '7': '7. 发送不含数据，接收150K回应',
        },
        'data': data_150k
    }
}

# 获取服务器地址
server_input = input("请输入服务器地址 (格式: ip:port)，默认 208.64.254.12:11111：") or "208.64.254.12:11111"
server_ip, server_port = server_input.split(':')
server_url = f'http://{server_ip}:{server_port}/test'

# 选择测试类别
print("请选择测试类别：")
for key, value in test_categories.items():
    print(f"{key}. {value['description']}")
category_choice = input("请输入测试类别编号（1-2）：")

if category_choice not in test_categories:
    print("无效的选择")
    exit(1)

# 输入测试次数
try:
    test_count = int(input("请输入测试次数（默认300次）：") or 300)
except ValueError:
    print("无效的输入，使用默认值300")
    test_count = 300

# 预热次数
warmup_count = 10

# 获取公网 IP
try:
    public_ip = requests.get('https://api.ipify.org').text
except requests.RequestException:
    public_ip = 'N/A'

# 获取本地时区的当前时间
local_time = datetime.datetime.now(timezone.utc).astimezone()
current_time = local_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')

# 获取主机名
hostname = socket.gethostname()

# 记录所有测试结果
all_results = []

# 执行每个子测试
for sub_test_choice, sub_test_description in test_categories[category_choice]['sub_tests'].items():
    print(f"\n开始子测试：{sub_test_description}")

    # 选择发送的数据
    if sub_test_choice in ['2', '3', '5', '6']:
        data = test_categories[category_choice]['data']
    else:
        data = b''

    # 记录子测试结果
    results = []

    # 预热
    print(f"开始预热测试，共{warmup_count}次...")
    for _ in range(warmup_count):
        try:
            response = requests.post(server_url, headers={'Test-Type': sub_test_choice}, data=data)
        except requests.RequestException as e:
            print(f"预热测试时出现错误：{e}")
            continue

    # 正式测试
    print(f"开始正式测试，共{test_count}次...")
    for i in range(test_count):
        start_time = time.time()
        try:
            response = requests.post(server_url, headers={'Test-Type': sub_test_choice}, data=data)
            end_time = time.time()
            elapsed_time = (end_time - start_time) * 1000  # 转换为毫秒
            results.append(elapsed_time)
            print(f"第{i + 1}次测试耗时：{elapsed_time:.2f} ms")
        except requests.RequestException as e:
            print(f"第{i + 1}次测试时出现错误：{e}")
            results.append(None)  # 记录错误
            continue

    # 过滤掉失败的测试
    successful_results = [r for r in results if r is not None]

    if successful_results:
        # 统计结果
        min_time = min(successful_results)
        max_time = max(successful_results)
        avg_time = sum(successful_results) / len(successful_results)
    else:
        min_time = max_time = avg_time = float('nan')

    # 输出子测试结果
    print("\n子测试完成！")
    print(f"测试时间：{current_time}")
    print(f"测试类别：{test_categories[category_choice]['description']}")
    print(f"子测试类型：{sub_test_description}")
    print(f"测试次数：{test_count}")
    print(f"成功次数：{len(successful_results)}")
    print(f"失败次数：{test_count - len(successful_results)}")
    print(f"公网 IP：{public_ip}")
    print(f"主机名：{hostname}")
    print(f"最短时间：{min_time:.2f} ms")
    print(f"最长时间：{max_time:.2f} ms")
    print(f"平均时间：{avg_time:.2f} ms")

    # 保存子测试结果
    all_results.append({
        '测试时间': current_time,
        '测试类别': test_categories[category_choice]['description'],
        '子测试类型': sub_test_description,
        '测试次数': test_count,
        '成功次数': len(successful_results),
        '失败次数': test_count - len(successful_results),
        '公网 IP': public_ip,
        '主机名': hostname,
        '最短时间': f"{min_time:.2f} ms",
        '最长时间': f"{max_time:.2f} ms",
        '平均时间': f"{avg_time:.2f} ms",
    })

# 保存所有结果到日志文件，追加模式
with open('result.txt', 'a') as f:
    for result in all_results:
        f.write("\n")
        for key, value in result.items():
            f.write(f"{key}：{value}\n")
        f.write("-" * 30 + "\n")

print("所有测试结果已保存到 result.txt")
