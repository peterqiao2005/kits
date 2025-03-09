#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")

apt-get update

mkdir /data/huggingface
mv /root/.cache/huggingface /data/

ln -s /data/huggingface /root/.cache/huggingface
ls -l /root/.cache

mkdir -p ~/miniconda3
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda3/miniconda.sh
bash ~/miniconda3/miniconda.sh -b -u -p ~/miniconda3
rm ~/miniconda3/miniconda.sh
source ~/miniconda3/bin/activate

conda create -n vllm python=3.12 -y
conda activate vllm

pip install vllm==0.7.3

nohup huggingface-cli download deepseek-ai/dDeepSeek-V3 2>&1 &
nohup huggingface-cli download deepseek-ai/dDeepSeek-R1 2>&1 &


# 自我删除
history -c
rm -- "$SCRIPT_PATH"