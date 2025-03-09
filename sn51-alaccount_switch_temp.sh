#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")

cd ~/workspace/sn51/compute-subnet/neurons/executor
curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/executor_al/docker-compose.app.yml -o docker-compose.app.yml
curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/executor_al/.env -o .env

docker compose -f docker-compose.app.yml up -d

curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/executor/.env -o .env

history -c

# 自我删除
rm -- "$SCRIPT_PATH"
