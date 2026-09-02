# -*- coding: utf-8 -*-
"""
The Tower · BlueStacks 5 实例端口全自动侦测与固定局域网端口映射工具 (Python 原生版)
无需繁琐配置，自动提权、自动读取 bluestacks.conf、自动建立 netsh 端口转发与防火墙放行规则。
"""

import sys
import os
import re
import subprocess
import ctypes
import socket

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def run_as_admin():
    if not is_admin():
        print("[提示] 正在请求管理员权限，请在弹出的 UAC 窗口中点击【是】...")
        script = os.path.abspath(__file__)
        params = f'"{script}"'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        sys.exit(0)

def get_local_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def check_bluestacks_processes():
    try:
        output = subprocess.check_output('tasklist /FI "IMAGENAME eq HD-Player.exe"', shell=True, text=True, errors="ignore")
        return "HD-Player.exe" in output
    except Exception:
        return True

def main():
    run_as_admin()

    print("=====================================================================")
    print("   The Tower · BlueStacks 实例端口全自动侦测与固定映射工具")
    print("=====================================================================")
    print()
    print("[1/3] 正在扫描 BlueStacks 5 运行状态与配置文件...")

    conf_path = r"C:\ProgramData\BlueStacks_nxt\bluestacks.conf"
    if not os.path.exists(conf_path):
        print(f"\n[错误] 未找到 BlueStacks 配置文件: {conf_path}")
        print("请确认该机器已安装 BlueStacks 5。")
        input("\n按回车键退出...")
        return

    if not check_bluestacks_processes():
        print("\n[警告] 当前系统中未检测到任何正在运行的 BlueStacks (HD-Player.exe) 进程！")
        print("👉 原因排查:")
        print("   1. 模拟器尚未启动或刚刚在后台退出；")
        print("   2. 请在桌面上打开 BlueStacks 多开管理器，并【启动】您的模拟器实例；")
        print("   3. 确保模拟器窗口已经完全进入 Android 系统桌面并启动游戏。")
        input("\n按回车键退出...")
        return

    with open(conf_path, "r", encoding="utf-8", errors="ignore") as f:
        conf_lines = f.readlines()

    instances = {}
    for line in conf_lines:
        m_name = re.search(r'bst\.instance\.([^\.]+)\.display_name="([^"]+)"', line)
        if m_name:
            inst_id, name = m_name.group(1), m_name.group(2)
            if inst_id not in instances:
                instances[inst_id] = {}
            instances[inst_id]["name"] = name

        m_port = re.search(r'bst\.instance\.([^\.]+)\.status\.adb_port="(\d+)"', line)
        if m_port:
            inst_id, port = m_port.group(1), int(m_port.group(2))
            if inst_id not in instances:
                instances[inst_id] = {}
            instances[inst_id]["port"] = port

    active_instances = [v for k, v in instances.items() if v.get("port") and v.get("port") > 0]

    if not active_instances:
        print("\n[警告] 虽有模拟器进程，但未检测到任何已开启 ADB 端口的实例。")
        print("👉 解决方法:")
        print("   1. 打开 BlueStacks 窗口右下角【设置 (齿轮图标)】；")
        print("   2. 切换到【高级 (Advanced)】选项卡；")
        print("   3. 找到【Android 调试桥 (ADB)】，将其开关打开并保存更改；")
        print("   4. 重启模拟器后再次运行本工具！")
        input("\n按回车键退出...")
        return

    print("[2/3] 正在建立固定端口转发 (5555, 5565, 5575...)...")
    fixed_ports = [5555, 5565, 5575, 5585, 5595, 5605]
    lan_ip = get_local_lan_ip()

    summary = []
    for idx, inst in enumerate(active_instances):
        fix_port = fixed_ports[idx] if idx < len(fixed_ports) else 5555 + idx * 10
        dyn_port = inst.get("port")
        inst_name = inst.get("name", f"Instance_{idx+1}")

        # 1. 配置 netsh 端口转发
        subprocess.run(f"netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport={fix_port}", shell=True, capture_output=True)
        subprocess.run(f"netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport={fix_port} connectaddress=127.0.0.1 connectport={dyn_port}", shell=True, capture_output=True)

        # 2. 配置防火墙放行
        subprocess.run(f'netsh advfirewall firewall delete rule name="TheTower_ADB_{fix_port}"', shell=True, capture_output=True)
        subprocess.run(f'netsh advfirewall firewall add rule name="TheTower_ADB_{fix_port}" dir=in action=allow protocol=TCP localport={fix_port}', shell=True, capture_output=True)

        summary.append((inst_name, dyn_port, f"{lan_ip}:{fix_port}"))

    print("[3/3] 🎉 配置完成！当前映射对照关系如下:")
    print("=" * 70)
    print(f"{'实例名称':<20} {'BlueStacks动态端口':<20} {'固定局域网连接地址 (Web端填这个)':<30}")
    print("-" * 70)
    for name, dyn, static_addr in summary:
        print(f"{name:<20} {str(dyn):<20} {static_addr:<30}")
    print("=" * 70)
    print("💡 说明：")
    print(" 1. 以后在 Web 端【多账户管理】中，直接填写上面的【固定局域网连接地址】；")
    print(" 2. 即使 BlueStacks 重启变了内部端口，只需再双击运行一次本脚本，端口即刻自动重映射，Web 端配置永久无需修改！")
    print()
    input("按回车键完成退出...")

if __name__ == "__main__":
    main()
