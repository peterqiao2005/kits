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
grep "^[[:space:]]\\{2\\}${container}:" docker-compose.yaml
if [ $? -ne 0 ]; then
    echo "容器 ${container} 未在 docker-compose.yaml 中找到."
    exit 1
fi

# 利用 awk 过滤 docker-compose.yaml，仅保留 version、services 和目标服务的完整配置
awk -v target="$container" '
BEGIN {
    in_services = 0;
    printing = 0;
}
/^version:/ {
    print;
    next;
}
/^services:/ {
    print;
    in_services = 1;
    next;
}
{
    if (in_services) {
        # 若遇空行，在目标块内则打印
        if ($0 ~ /^[[:space:]]*$/) {
            if (printing) { print }
            next;
        }
        # 计算当前行前面的空格数（缩进）
        orig = $0;
        line = orig;
        sub(/^[ ]*/, "", line);
        indent = length(orig) - length(line);
        # 判断是否为服务头（缩进正好为2个空格）
        if (indent == 2) {
            pattern = "  " target ":";
            if (index(orig, pattern) == 1) {
                printing = 1;
                base_indent = indent;
                print;
            } else {
                printing = 0;
            }
        } else if (printing && indent > base_indent) {
            # 打印目标服务块中，缩进大于服务头的行
            print;
        }
    }
}
' docker-compose.yaml > docker-compose.tmp.yaml

# 使用过滤后的临时文件启动 docker-compose 服务
docker-compose -f docker-compose.tmp.yaml up -d

# 用过滤后的文件替换原文件
mv docker-compose.tmp.yaml docker-compose.yaml
