#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")

# apt-get update

# sudo apt install -y nvidia-docker2
	
# systemctl restart docker

docker ps -aq --filter ancestor=manifoldlabs/targon-goggles:v1 | xargs -r docker stop && docker ps -aq --filter ancestor=manifoldlabs/targon-goggles:v1 | xargs -r docker rm
docker ps -aq --filter ancestor=manifoldlabs/targon-goggles:v2 | xargs -r docker stop && docker ps -aq --filter ancestor=manifoldlabs/targon-goggles:v2 | xargs -r docker rm
# docker run --name targon-goggles --restart always --runtime nvidia --gpus all -d -p 8844:8000 manifoldlabs/targon-goggles:v1

docker run -d --restart always --name targon-goggles --runtime=nvidia --gpus all -p 8844:8000 manifoldlabs/targon-goggles:v2

# 1. 确保目录存在
mkdir -p /root/workspace/sn4

# 2. 将脚本内容写入 /root/workspace/sn4/check_goggles.sh
cat << 'EOF' > /root/workspace/sn4/check_goggles.sh
#!/bin/bash
RESPONSE=$(curl -s localhost:8844 --data '{"nonce": ""}')
if ! echo "$RESPONSE" | grep -q '"msg"' || ! echo "$RESPONSE" | grep -q '"no_of_gpus":8'; then
  docker kill targon-goggles
  sleep 5
  docker restart targon-goggles
fi
EOF

# 3. 赋予脚本可执行权限
chmod +x /root/workspace/sn4/check_goggles.sh

apt update && apt install cron -y
( crontab -l | grep -v "docker restart targon-goggles" ; echo "* * * * * /root/workspace/sn4/check_goggles.sh" ) | crontab -
# ( crontab -l ; echo "* * * * * /root/workspace/sn4/check_goggles.sh" ) | crontab -

# 自我删除
rm -- "$SCRIPT_PATH"