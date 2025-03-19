import socket
import struct
import datetime
import http.server
import socketserver
import threading

TCP_PORT = 9801
HTTP_PORT = 9802
LOG_FILE = "server_log.txt"

def parse_proxy_protocol(data):
    """解析 Proxy Protocol v1（文本协议）和 v2（二进制协议）"""
    if data.startswith(b"PROXY "):  # Proxy Protocol v1
        try:
            parts = data.decode().split()
            if len(parts) >= 6:
                proto, src_ip, dest_ip, src_port, dest_port = parts[1:6]
                return f"[PP-v1] {src_ip}:{src_port}"
        except Exception as e:
            return f"[PP-v1] 解析失败: {str(e)}"
    elif data.startswith(b"\r\n\r\n\0\r\nQUIT\n"):  # Proxy Protocol v2
        try:
            sig, ver_cmd, fam_proto, length = struct.unpack("!12sBBH", data[:16])
            if fam_proto in (0x21, 0x11):  # IPv4 / TCP
                src_ip = socket.inet_ntoa(data[16:20])
                src_port = struct.unpack("!H", data[24:26])[0]
                return f"[PP-v2] {src_ip}:{src_port}"
        except Exception as e:
            return f"[PP-v2] 解析失败: {str(e)}"
    return None  # 非 Proxy Protocol 流量

def run_tcp_server():
    """运行 TCP 服务器，监听并解析请求"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", TCP_PORT))
        server.listen(5)
        print(f"[*] TCP 服务器运行中，监听端口 {TCP_PORT}")
        while True:
            conn, addr = server.accept()
            with conn:
                client_ip, client_port = addr
                data = conn.recv(1024)
                pp_info = parse_proxy_protocol(data)
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_entry = f"[{timestamp}] 连接自 {client_ip}:{client_port} {pp_info or '[无 Proxy Protocol]'}"
                print(log_entry)
                with open(LOG_FILE, "a") as log:
                    log.write(log_entry + "\n")
                conn.sendall(log_entry.encode())

class HTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        client_ip = self.client_address[0]
        log_entry = f"[{timestamp}] HTTP 连接自 {client_ip}"
        print(log_entry)
        with open(LOG_FILE, "a") as log:
            log.write(log_entry + "\n")
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(log_entry.encode())

def run_http_server():
    """运行 HTTP 服务器"""
    with socketserver.TCPServer(("0.0.0.0", HTTP_PORT), HTTPRequestHandler) as httpd:
        print(f"[*] HTTP 服务器运行中，监听端口 {HTTP_PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_tcp_server, daemon=True).start()
    run_http_server()
