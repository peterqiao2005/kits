import pyautogui
import keyboard
import time
import threading

# 用于存储三个鼠标位置
points = [None, None, None]

click_intervals = [0.1,0.5,5]

# 用于控制自动点击的标志
clicking = False

# 记录鼠标位置
def record_position(index):
    x, y = pyautogui.position()
    points[index] = (x, y)
    print(f"记录位置 {index+1}: {x}, {y}")

# 自动点击函数
def auto_click():
    global clicking
    while clicking:
        if points[0] is not None:
            pyautogui.click(points[0])
            time.sleep(click_intervals[0])  # 第1个点每0.1秒点击一次

        if points[1] is not None:
            pyautogui.click(points[1])
            time.sleep(click_intervals[1])  # 第2个点每0.5秒点击一次

        if points[2] is not None:
            pyautogui.click(points[2])
            time.sleep(click_intervals[3])    # 第3个点每5秒点击一次

# 开始自动点击
def start_clicking():
    global clicking
    if not clicking:
        clicking = True
        print("开始自动点击")
        threading.Thread(target=auto_click).start()

# 停止自动点击
def stop_clicking():
    global clicking
    clicking = False
    print("停止自动点击")

# 绑定快捷键
keyboard.add_hotkey('ctrl+shift+1', lambda: record_position(0))  # 记录第一个点
keyboard.add_hotkey('ctrl+shift+2', lambda: record_position(1))  # 记录第二个点
keyboard.add_hotkey('ctrl+shift+3', lambda: record_position(2))  # 记录第三个点
keyboard.add_hotkey('ctrl+shift+s', start_clicking)              # 开始点击
keyboard.add_hotkey('ctrl+shift+q', stop_clicking)               # 停止点击

print(f"按 'ctrl+shift+1' 记录第一个点，每{click_intervals[0]}秒点击一次")
print(f"按 'ctrl+shift+2' 记录第二个点，每{click_intervals[1]}秒点击一次")
print(f"按 'ctrl+shift+3' 记录第三个点，每{click_intervals[2]}秒点击一次")      
print("按 'ctrl+shift+s' 开始自动点击，按 'ctrl+shift+q' 停止自动点击")
print("按 'esc' 退出程序")

# 保持程序运行
keyboard.wait('esc')  # 按下 'esc' 退出程序
