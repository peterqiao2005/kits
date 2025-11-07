import os
import json
import requests
from datetime import datetime

LOG_PATH = "/var/log/openvpn_dns_update.log"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(full_msg + "\n")
        f.flush()  # 立即写入

def load_config():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 脚本所在目录
    config_file = os.path.join(BASE_DIR, "cloudflare-api.conf")
    if not os.path.exists(config_file):
        raise Exception(f"{config_file} 文件未找到，请创建并填写 Cloudflare API 配置信息。")

    with open(config_file) as f:
        config = {}
        for line in f:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                config[key] = value
        return config

def get_zone_id(domain, config):
    url = f"https://api.cloudflare.com/client/v4/zones?name={domain}"
    headers = {
        "Authorization": f"Bearer {config['CF_API_KEY']}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    response_data = response.json()

    if response_data["success"]:
        return response_data["result"][0]["id"]
    else:
        raise Exception(f"无法获取 Zone ID: {response_data['errors']}")

def record_exists(zone_id, record_type, name, config):
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?type={record_type}&name={name}"
    headers = {
        "Authorization": f"Bearer {config['CF_API_KEY']}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    response_data = response.json()

    if response_data["success"] and response_data["result"]:
        return response_data["result"][0]["id"]
    return None

def create_or_update_record(zone_id, record_type, name, content, ttl, priority, config):
    existing_record_id = record_exists(zone_id, record_type, name, config)
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
    headers = {
        "Authorization": f"Bearer {config['CF_API_KEY']}",
        "Content-Type": "application/json"
    }
    data = {
        "type": record_type,
        "name": name,
        "content": content,
        "ttl": ttl
    }
    if priority is not None:
        data["priority"] = priority

    if existing_record_id:
        update_url = f"{url}/{existing_record_id}"
        response = requests.put(update_url, headers=headers, json=data)
        response_data = response.json()
        if response_data["success"]:
            log(f"✅ 更新 {record_type} 记录 {name} 成功。")
        else:
            log(f"❌ 更新 {record_type} 记录 {name} 失败: {response_data['errors']}")
    else:
        response = requests.post(url, headers=headers, json=data)
        response_data = response.json()
        if response_data["success"]:
            log(f"✅ 创建 {record_type} 记录 {name} 成功。")
        else:
            log(f"❌ 创建 {record_type} 记录 {name} 失败: {response_data['errors']}")

def get_external_ip():
    ip_services = [
        "https://api.ipify.org",
        "https://ipinfo.io/ip",
        "http://ip.gs",
        "https://ifconfig.me/ip"
    ]
    for url in ip_services:
        try:
            log(f"尝试从 {url} 获取公网 IP...")
            if "ip.gs" in url:
                res = requests.get(url, timeout=5)
                ip = res.json().get("ip")
                if ip:
                    return ip
            else:
                res = requests.get(url, timeout=5)
                res.raise_for_status()
                return res.text.strip()
        except Exception as e:
            log(f"⚠️ 获取 IP 失败 ({url}): {e}")
    raise Exception("❌ 所有公网 IP 服务均失败，无法获取 IP")

def main():
    log("===== 开始 DNS 更新任务 =====")
    try:
        config = load_config()
        domain = "3518.pro"

        log("获取 Zone ID...")
        zone_id = get_zone_id(domain, config)

        log("获取公网 IP...")
        external_ip = get_external_ip()
        log(f"成功获取公网 IP: {external_ip}")

        fqdn = f"vpn-shanghai.{domain}"
        log(f"处理 DNS A 记录: {fqdn}")
        create_or_update_record(zone_id, "A", fqdn, external_ip, 3600, None, config)

        log("✅ DNS 更新完成")
    except Exception as e:
        log(f"❌ 脚本异常: {e}")
    log("===== 任务结束 =====\n")

if __name__ == "__main__":
    main()

