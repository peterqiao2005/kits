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
test_types = {
    '1': '1. 不含数据，仅测算请求到响应的时间差',
    '2': '2. 发送4K数据，接收4K回应',
    '3': '3. 发送4K数据，无回应',
    '4': '4. 发送不含数据，接收4K回应',
    '5': '5. 发送150K数据，接收150K回应',
    '6': '6. 发送150K数据，无回应',
    '7': '7. 发送不含数据，接收150K回应',
}

# 选择测试类型
print("请选择测试类型：")
for key, value in test_types.items():
    print(value)
choice = input("请输入测试类型编号（1-7）：")

if choice not in test_types:
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

# 服务器地址
server_url = 'http://208.64.254.12:11111/test'

# 选择发送的数据
if choice in ['2', '3']:
    data = data_4k
elif choice in ['5', '6']:
    data = data_150k
else:
    data = b''

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

# 记录测试结果
results = []

# 预热
print(f"开始预热测试，共{warmup_count}次...")
for _ in range(warmup_count):
    response = requests.post(server_url, headers={'Test-Type': choice}, data=data)

# 正式测试
print(f"开始正式测试，共{test_count}次...")
for i in range(test_count):
    start_time = time.time()
    response = requests.post(server_url, headers={'Test-Type': choice}, data=data)
    end_time = time.time()
    elapsed_time = (end_time - start_time) * 1000  # 转换为毫秒
    results.append(elapsed_time)
    print(f"第{i + 1}次测试耗时：{elapsed_time:.2f} ms")

# 统计结果
min_time = min(results)
max_time = max(results)
avg_time = sum(results) / len(results)

# 输出结果
print("\n测试完成！")
print(f"测试时间：{current_time}")
print(f"测试类型：{test_types[choice]}")
print(f"公网 IP：{public_ip}")
print(f"主机名：{hostname}")
print(f"最短时间：{min_time:.2f} ms")
print(f"最长时间：{max_time:.2f} ms")
print(f"平均时间：{avg_time:.2f} ms")

# 保存结果到日志文件，追加模式
with open('result.txt', 'a') as f:
    f.write(f"\n测试时间：{current_time}\n")
    f.write(f"测试类型：{test_types[choice]}\n")
    f.write(f"公网 IP：{public_ip}\n")
    f.write(f"主机名：{hostname}\n")
    f.write(f"最短时间：{min_time:.2f} ms\n")
    f.write(f"最长时间：{max_time:.2f} ms\n")
    f.write(f"平均时间：{avg_time:.2f} ms\n")
    f.write("-" * 30 + "\n")

print("结果已保存到 result.txt")