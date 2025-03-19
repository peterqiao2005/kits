#!/bin/bash

# 允许的受信任 IP（无需限制）
TRUSTED_IPS=(
    "94.156.8.133" "160.202.129.187" "34.91.174.145" "186.233.185.213"
    "207.211.187.170" "160.202.129.179" "124.158.103.103" "52.54.133.35"
    "162.244.80.223" "162.244.82.166" "198.145.121.215" "210.186.104.113/16"
    "118.100.2.69/16" "180.75.8.37/16" "192.150.253.122" "207.211.187.170"
    "34.142.251.211" "34.122.248.160" "122.11.227.206" "35.195.128.110"
    "185.8.107.242" "94.156.8.145" "23.251.116.164" "159.89.229.121"
    "54.175.59.42" "178.156.135.234" "180.75.8.37" "3.134.238.10"
    "3.129.111.220" "162.244.81.79"
)

# **始终允许以下 IP 访问（防止 SSH 断开）**
ALWAYS_ALLOWED_IPS=(
    "162.244.80.223" "162.244.82.166" "198.145.121.215"
    "210.186.104.113/16" "118.100.2.69/16" "180.75.8.37/16"
)

# 允许的 Cloudflare IP（Proxy Protocol 使用）
CF_IPS=(
    "173.245.48.0/20" "103.21.244.0/22" "103.22.200.0/22" "103.31.4.0/22"
)

# 允许的内网 IP（无需限制）
PRIVATE_NETWORKS=("192.168.0.0/16" "172.16.0.0/12" "10.0.0.0/8")

# 受限访问的端口范围
ALLOWED_PORT_RANGE="9001:9999"

# **清理旧规则，避免误伤外网访问**
iptables -F
iptables -X
iptables -P INPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -P OUTPUT ACCEPT

# **修复 xtables-addons 加载问题**
modprobe xt_TPROXY 2>/dev/null
modprobe xt_connlimit 2>/dev/null
modprobe xt_string 2>/dev/null

# **安装依赖**
# apt update && apt install -y xtables-addons-common ipset iptables-persistent

# **确保 SSH 连接 IP 永不删除**
iptables -D INPUT -m set --match-set always_allowed src -j ACCEPT 2>/dev/null
iptables -D INPUT -p tcp --dport 22 -m set --match-set always_allowed src -j ACCEPT 2>/dev/null

ipset destroy always_allowed 2>/dev/null
ipset destroy trusted_ips 2>/dev/null
ipset destroy cf_ips 2>/dev/null
ipset destroy private_ips 2>/dev/null
sleep 1

ipset create always_allowed hash:net maxelem 1048576 hashsize 65536 timeout 0
ipset create trusted_ips hash:net maxelem 1048576 hashsize 65536 timeout 0
ipset create cf_ips hash:net maxelem 1048576 hashsize 65536 timeout 0
ipset create private_ips hash:net maxelem 100 timeout 0

for ip in "${ALWAYS_ALLOWED_IPS[@]}"; do
    ipset add always_allowed "$ip" -exist
done

iptables -A INPUT -m set --match-set always_allowed src -j ACCEPT
iptables -A INPUT -p tcp --dport 22 -m set --match-set always_allowed src -j ACCEPT

for ip in "${TRUSTED_IPS[@]}"; do
    ipset add trusted_ips "$ip" -exist
done

for ip in "${CF_IPS[@]}"; do
    ipset add cf_ips "$ip" -exist
done

for ip in "${PRIVATE_NETWORKS[@]}"; do
    ipset add private_ips "$ip" -exist
done

# **允许 DNS 解析**
iptables -A INPUT -p udp --sport 53 -j ACCEPT
iptables -A INPUT -p tcp --sport 53 -j ACCEPT
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# **允许 ICMP (ping)**
iptables -A INPUT -p icmp --icmp-type echo-request -j ACCEPT
iptables -A INPUT -p icmp --icmp-type echo-reply -j ACCEPT
iptables -A OUTPUT -p icmp --icmp-type echo-request -j ACCEPT
iptables -A OUTPUT -p icmp --icmp-type echo-reply -j ACCEPT

# **允许所有出站流量**
iptables -A OUTPUT -m state --state NEW,ESTABLISHED,RELATED -j ACCEPT

# **应用新规则**
iptables -A INPUT -m set --match-set trusted_ips src -p tcp --dport $ALLOWED_PORT_RANGE -j ACCEPT
iptables -A INPUT -m set --match-set cf_ips src -p tcp --dport $ALLOWED_PORT_RANGE -j ACCEPT
iptables -A INPUT -m set --match-set private_ips src -p tcp --dport $ALLOWED_PORT_RANGE -j ACCEPT
# iptables -A INPUT -m set --match-set cf_ips src -p tcp --dport $ALLOWED_PORT_RANGE  -m string --algo bm --string "PROXY " -j ACCEPT
iptables -A INPUT -p tcp --dport $ALLOWED_PORT_RANGE -m connlimit --connlimit-above 50 --connlimit-mask 32 -j DROP

# **拒绝未授权 IP 访问受限端口**
iptables -A INPUT -p tcp --dport $ALLOWED_PORT_RANGE -j DROP

# 限制 SYN Flood 攻击
iptables -A INPUT -p tcp --syn -m hashlimit --hashlimit 10/sec --hashlimit-burst 20 --hashlimit-mode srcip --hashlimit-name synlimit -j ACCEPT
iptables -A INPUT -p tcp --syn -j DROP

# **修复 Proxy Protocol 解析问题**
iptables -A INPUT -p tcp --dport 65001 -j ACCEPT
iptables -A INPUT -p tcp --dport 9801 -j ACCEPT
iptables -A INPUT -p tcp --dport 9802 -j ACCEPT

# 防止 Proxy Protocol 伪造攻击
iptables -A INPUT -p tcp -m string --algo bm --hex-string "|50524F5859|" -j DROP

# **显式拒绝所有非受信 IP**
iptables -A INPUT -j DROP

# **全局默认拒绝所有未匹配流量**
iptables -P INPUT DROP

# **保存规则，确保重启后仍然生效**
netfilter-persistent save
netfilter-persistent reload
