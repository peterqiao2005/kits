#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")

apt-get update

# sudo apt install -y nvidia-docker2
	
# systemctl restart docker

docker ps -aq --filter ancestor=manifoldlabs/targon-goggles:v1 | xargs -r docker stop && docker ps -aq --filter ancestor=manifoldlabs/targon-goggles:v1 | xargs -r docker rm

docker run --name targon-goggles --restart always --runtime nvidia --gpus all -d -p 8844:8000 manifoldlabs/targon-goggles:v1
( crontab -l ; echo "*/10 * * * * /usr/bin/docker restart targon-goggles" ) | crontab -

# 自我删除
rm -- "$SCRIPT_PATH"