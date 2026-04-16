import threading
import time

import keyboard
import pyautogui


points = [None, None, None]
click_intervals = [0.1, 0.5, 5]

clicking = False
click_thread = None
state_lock = threading.Lock()


def record_position(index):
    x, y = pyautogui.position()
    points[index] = (x, y)
    print(f"记录位置 {index + 1}: {x}, {y}")


def auto_click():
    next_click_times = [time.monotonic()] * len(points)

    while True:
        with state_lock:
            if not clicking:
                break
            current_points = points[:]

        now = time.monotonic()

        for index, point in enumerate(current_points):
            if point is None:
                next_click_times[index] = now
                continue

            if now >= next_click_times[index]:
                pyautogui.click(point)
                next_click_times[index] = now + click_intervals[index]

        time.sleep(0.01)


def start_clicking():
    global clicking, click_thread

    with state_lock:
        if clicking:
            print("自动点击已经在运行中")
            return
        clicking = True

    print("开始自动点击")
    click_thread = threading.Thread(target=auto_click, daemon=True)
    click_thread.start()


def stop_clicking():
    global clicking

    with state_lock:
        if not clicking:
            print("自动点击当前未运行")
            return
        clicking = False

    print("停止自动点击")


keyboard.add_hotkey("ctrl+shift+1", lambda: record_position(0))
keyboard.add_hotkey("ctrl+shift+2", lambda: record_position(1))
keyboard.add_hotkey("ctrl+shift+3", lambda: record_position(2))
keyboard.add_hotkey("ctrl+shift+s", start_clicking)
keyboard.add_hotkey("ctrl+shift+q", stop_clicking)

print(f"按 'ctrl+shift+1' 记录第一个点，每 {click_intervals[0]} 秒点击一次")
print(f"按 'ctrl+shift+2' 记录第二个点，每 {click_intervals[1]} 秒点击一次")
print(f"按 'ctrl+shift+3' 记录第三个点，每 {click_intervals[2]} 秒点击一次")
print("按 'ctrl+shift+s' 开始自动点击，按 'ctrl+shift+q' 停止自动点击")
print("按 'esc' 退出程序")

keyboard.wait("esc")
stop_clicking()
