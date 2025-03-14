import socket
import requests
import datetime
import argparse
import http.server
import socketserver
import threading

def get_public_ip():
    """尝试从多个服务获取公网 IPv4 地址"""
    ip_services = [
        "https://api64.ipify.org?format=text",
        "https://checkip.amazonaws.com/",
        "https://ifconfig.me/ip",
        "https://ident.me/"
    ]
    
    for service in ip_services:
        try:
            response = requests.get(service, timeout=5)
            if response.status_code == 200:
                return response.text.strip()
        except requests.RequestException:
            continue
    
    return "未知"

def send_tcp_request(server_ip, server_port, use_proxy_protocol):
    """客户端连接服务器并发送 TCP 请求"""
    client_ip = get_public_ip()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if use_proxy_protocol:
        proxy_protocol_header = f"PROXY TCP4 {client_ip} {server_ip} 54321 {server_port}\r\n"
    else:
        proxy_protocol_header = ""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((server_ip, server_port))
        sock.sendall(proxy_protocol_header.encode() + b"Hello Server!")

        response = sock.recv(1024).decode()
        print(f"[{timestamp}] 你的公网IP: {client_ip}")
        print(f"[{timestamp}] 服务器响应: {response}")

def send_http_request(server_ip, server_port):
    """客户端连接服务器并发送 HTTP 请求"""
    client_ip = get_public_ip()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    url = f"http://{server_ip}:{server_port}/"
    
    try:
        response = requests.get(url, timeout=5)
        print(f"[{timestamp}] 你的公网IP: {client_ip}")
        print(f"[{timestamp}] 服务器响应: {response.text}")
    except requests.RequestException as e:
        print(f"[{timestamp}] HTTP 请求失败: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TCP & HTTP 客户端测试 Proxy Protocol")
    parser.add_argument("server_ip", type=str, help="服务器 IP 地址")
    parser.add_argument("--port", type=int, default=65001, help="TCP 服务器端口，默认为 65001")
    parser.add_argument("--http-port", type=int, default=65002, help="HTTP 服务器端口，默认为 65002")
    parser.add_argument("--no-pp", action="store_true", help="禁用 Proxy Protocol (仅 TCP)")
    parser.add_argument("--http", action="store_true", help="使用 HTTP 测试而非 TCP")
    
    args = parser.parse_args()
    
    if args.http:
        send_http_request(args.server_ip, args.http_port)
    else:
        send_tcp_request(args.server_ip, args.port, not args.no_pp)