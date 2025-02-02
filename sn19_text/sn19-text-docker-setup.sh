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
# 处理 version 和 services 之前的部分，直接打印
/^version:/ { print; next }
/^services:/ { print; in_services=1; next }

{
    if (in_services) {
        # 如果遇到空行，若当前正在打印目标服务块则输出，否则跳过
        if ($0 ~ /^[[:space:]]*$/) {
            if (printing) { print }
            next
        }
        # 获取当前行前面的空格数（缩进）
        match($0, /^([ ]*)/, arr)
        indent = length(arr[1])
        # 如果缩进为2，则认为是服务头行
        if (indent == 2) {
            if ($0 ~ ("^[ ]{2}"target":")) {
                printing = 1
                base_indent = indent
                print
            } else {
                printing = 0
            }
        }
        else if (printing && indent > base_indent) {
            # 只打印目标服务块内，缩进大于服务头的内容
            print
        }
    }
    else {
        print
    }
}
' docker-compose.yaml > docker-compose.tmp.yaml

# 使用过滤后的临时文件启动 docker-compose 服务
docker-compose -f docker-compose.tmp.yaml up -d

# 删除临时文件
rm docker-compose.tmp.yaml
