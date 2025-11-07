## === 文件: app.py ===

from flask import Flask, render_template, request, jsonify
import json
import os
import socket
import binascii

app = Flask(__name__)

DEVICE_FILE = 'devices.json'

# ========== Wake-on-LAN 核心函数 ==========
def send_magic_packet(mac, ip='192.168.1.255', port=9):
    mac = mac.replace(':', '').replace('-', '')
    if len(mac) != 12:
        raise ValueError("Invalid MAC address")
    data = b'\xff' * 6 + binascii.unhexlify(mac * 16)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(data, (ip, port))

# ========== 读取/保存设备信息 ==========
def load_devices():
    if not os.path.exists(DEVICE_FILE):
        return []
    with open(DEVICE_FILE, 'r') as f:
        return json.load(f)

def save_devices(devices):
    with open(DEVICE_FILE, 'w') as f:
        json.dump(devices, f, indent=2)

# ========== 路由定义 ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/devices', methods=['GET'])
def get_devices():
    return jsonify(load_devices())

@app.route('/api/devices', methods=['POST'])
def add_device():
    data = request.json
    devices = load_devices()
    devices.append(data)
    save_devices(devices)
    return jsonify({'status': 'ok'})

@app.route('/api/devices/<int:index>', methods=['PUT'])
def update_device(index):
    data = request.json
    devices = load_devices()
    if index < 0 or index >= len(devices):
        return jsonify({'error': 'Invalid index'}), 400
    devices[index] = data
    save_devices(devices)
    return jsonify({'status': 'ok'})

@app.route('/api/devices/<int:index>', methods=['DELETE'])
def delete_device(index):
    devices = load_devices()
    if index < 0 or index >= len(devices):
        return jsonify({'error': 'Invalid index'}), 400
    devices.pop(index)
    save_devices(devices)
    return jsonify({'status': 'ok'})

@app.route('/api/wake/<int:index>', methods=['POST'])
def wake_device(index):
    devices = load_devices()
    if index < 0 or index >= len(devices):
        return jsonify({'error': 'Invalid index'}), 400
    dev = devices[index]
    try:
        ip_parts = dev['ip'].split('.')
        if len(ip_parts) != 4:
            raise ValueError("Invalid IP address")
        broadcast_ip = '.'.join(ip_parts[:3]) + '.255'
        send_magic_packet(dev['mac'], broadcast_ip, int(dev.get('port', 9)))
        return jsonify({'status': 'sent'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
