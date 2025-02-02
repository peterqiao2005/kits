#!/bin/bash

mkdir -p ~/workspace/vllm-docker
cd ~/workspace/vllm-docker
curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/sn19_text/docker-compose.yaml -o docker-compose.yaml

# 提示用户输入容器名或数字（数字n代表vllm_n）
read -p "请输入要启动的容器名或数字(数字n代表vllm_n): " input
if [[ $input =~ ^[0-9]+$ ]]; then
    container="vllm_${input}"
else
    container="$input"
fi
echo "选择的容器为: $container"

# 用命令行检查 docker-compose.yaml 中是否存在该容器的定义
cat docker-compose.yaml | grep "^[[:space:]]\\{2\\}${container}:"
if [ $? -ne 0 ]; then
    echo "容器 ${container} 未在 docker-compose.yaml 中找到."
    exit 1
fi

# 利用 awk 过滤 docker-compose.yaml，仅保留选定的容器
awk -v target="$container" '
BEGIN { in_services=0; print_block=0; }
/^services:/ { in_services=1; print; next; }
{
  if (in_services && match($0, /^[ ]{2}([^:]+):/, arr)) {
      service = arr[1];
      if (service == target) {
          print_block=1;
          print;
          next;
      } else {
          print_block=0;
          next;
      }
  }
  if (in_services && print_block && match($0, /^[ ]{4}/)) {
      print;
      next;
  }
  if (!in_services) print;
}
' docker-compose.yaml > docker-compose.tmp.yaml

# 使用过滤后的临时文件启动 docker-compose 服务
docker-compose -f docker-compose.tmp.yaml up -d

# 删除临时文件
rm docker-compose.tmp.yaml
