#!/bin/bash

# 设置工作目录
WORKSPACE=~/workspace/openvpn
CLIENT_NAME=vpn-x86-johor
HOST_PORT=12294

# 创建工作目录
mkdir -p "$WORKSPACE"

# 生成 docker-compose.yml
cat > "$WORKSPACE/docker-compose.yml" <<EOF
version: '3'

services:
    openvpn:
        image: kylemanna/openvpn
        container_name: openvpn
        restart: unless-stopped
        ports:
            - "${HOST_PORT}:1194/udp"
        volumes:
            - ./data:/etc/openvpn
        cap_add:
            - NET_ADMIN
EOF

# 初始化 OpenVPN 配置
docker run --rm -v "$WORKSPACE/data:/etc/openvpn" kylemanna/openvpn ovpn_genconfig -u udp://$(hostname -I | awk '{print $1}'):${HOST_PORT}
docker run --rm -v "$WORKSPACE/data:/etc/openvpn" -e EASYRSA_BATCH=1 kylemanna/openvpn ovpn_initpki nopass

# 启动服务
cd "$WORKSPACE"
docker compose up -d

# 创建客户端配置
docker run --rm -v "$WORKSPACE/data:/etc/openvpn" kylemanna/openvpn easyrsa build-client-full $CLIENT_NAME nopass
docker run --rm -v "$WORKSPACE/data:/etc/openvpn" kylemanna/openvpn ovpn_getclient $CLIENT_NAME > "$WORKSPACE/${CLIENT_NAME}.ovpn"

echo "OpenVPN 部署完成，客户端配置文件在: $WORKSPACE/${CLIENT_NAME}.ovpn"