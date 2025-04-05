#!/bin/bash

# 如果没有提供密钥文件和 IP 列表，则提示用法后退出
if [ $# -lt 2 ]; then
  echo "Usage: $0 <SSH_PRIVATE_KEY> [IP_LIST_FILE] <COMMAND>"
  echo "Example: $0 /root/.ssh/id_rsa ip_list.txt 'uname -a'"
  exit 1
fi

# 读取第一个参数作为 SSH 私钥文件路径
KEY_FILE="$1"
# 读取第二个参数作为 IP 列表文件
IPS_FILE="$2"
shift 2  # 移除前两个参数，剩下的作为命令

# 确保命令不为空
if [ -z "$*" ]; then
  echo "Error: No command provided."
  exit 1
fi

COMMAND="$*"

# 逐行读取目标信息
while read -r line
do
  # 跳过空行
  [ -z "$line" ] && continue

  # 拆分 IP、端口、用户
  IFS=',' read -r ip port user <<< "$line"

  # 确保 IP 存在
  if [ -z "$ip" ]; then
    echo "Error: Invalid line format: $line"
    continue
  fi

  # 端口为空时默认 22
  [[ "$port" =~ ^[0-9]+$ ]] || port="22"
  # 用户为空时默认 root
  [ -z "$user" ] && user="root"

  echo "===== Executing command on $ip (port=$port, user=$user) ====="

  # 通过 SSH 连接执行命令
  ssh -o StrictHostKeyChecking=no -n -i "$KEY_FILE" -p "$port" "$user@$ip" "$COMMAND"

  echo
done < "$IPS_FILE"
