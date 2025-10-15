import pyautogui
import time

def main():
    # 等待2秒
    time.sleep(2)

    # 取鼠标当前位置
    x, y = pyautogui.position()

    while True:
        # 点击两次，间隔0.3秒
        pyautogui.click(x, y)
        time.sleep(0.3)
        pyautogui.click(x, y)

        # 等待4.5秒后再次点击
        time.sleep(3.5)

if __name__ == "__main__":
    main()
