#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")

#!/bin/bash

# 如果没有提供密钥文件参数，则提示用法后退出
if [ $# -lt 1 ]; then
  echo "Usage: $0 <SSH_PRIVATE_KEY> [IP_LIST_FILE]"
  echo "Example: $0 /root/.ssh/id_rsa ip_list.txt"
  exit 1
fi

# 读取第一个参数作为 SSH 私钥文件路径
KEY_FILE="$1"
# 如果第二个参数为空，则默认使用 ip_list.txt
IPS_FILE="${2:-ip_list.txt}"

# 逐行读取目标信息
while read -r line
do
  # 跳过空行
  [ -z "$line" ] && continue

  # 解析「IP,端口,用户名」
  ip=$(echo "$line" | cut -d',' -f1)
  port=$(echo "$line" | cut -d',' -f2)
  user=$(echo "$line" | cut -d',' -f3)

  # 如果端口为空，则默认 22
  [ -z "$port" ] && port="22"
  # 如果用户名为空，则默认 root
  [ -z "$user" ] && user="root"

  echo "===== Install TaoChaCha on $ip (port=$port, user=$user) ====="

  # 通过指定密钥 (-i) 和端口 (-p) 进行 SSH 登录并执行命令
  ssh -o StrictHostKeyChecking=no -n -i "$KEY_FILE" -p "$port" "$user@$ip" "curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/taochacha/taochacha-setup.sh | sudo bash"

  echo
done < "$IPS_FILE"

# 自我删除
# rm -- "$SCRIPT_PATH"
