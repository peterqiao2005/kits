#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")

apt-get update

apt install ufw curl sudo -y

sudo ufw allow 22
sudo ufw allow 3000:30000/tcp
sudo ufw allow 33000:65535/tcp
sudo ufw allow 3000:65535/udp

echo "y" | sudo ufw enable

sudo ufw status

rm -rf ~/.ssh/authorized_keys

echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC2iXvwkfyVXVtExxD/qOAb25Q20vmcvAEYBM/TBvjgpBB2lOYv22oyMIDWSa3qZWYWtDhCtWW/i7U7myp7tLxQ1tMh1xRhagBtdGMypILukYqIzgO+g3f/tyTfRjaIl8acL/iHvruZ62BaPzBsUyMHB7LUbUTB+q0WVF0xU3Qclkymmp3NcWvA/wTyTnFoW3wEP9iCnU+er4lEhYuMnrAHm6vi/LfmrP2A72ltk7QAW3/cMja8DRMOvt1x0NvrSTL4rD9AxdVDh2vOS0DMaKqWe/t7SVtbT4Whgsnd4XV+HarYRDq945kq2NmjgAyLEFKUkt4X6JJClE9W7WKiiYzJEDOQDCJRtTwVCreZOLANHITnZT77Z2ExT1DsMLNAAMxWjoSQNZx2847vG15eiHyNpUinmtxuYhtvV6t5SduWJU9zuUV7htsRkZUGgQW7eqLT8JAoErQtPR3r9zxstgi20YC9Yx3i8UwRykIrzsAoNgdWWrbJe5zbn1YqetOPlGL0er7PwWyGH8qpb4rNaJRf5wQlMz/ZAL8BrZZFRLyBj1F2lctx22cXgv7aYRDAW4fXGakHoJ5FBeqAB6uJyFD2kcGXfbWHcvrlaq0HrG/ox56hYHgp97omR3yZRRwyre2HmjjudznlbpmhCqvMfyVJ9MfLupzEqtDtNgp+BJ7bWw== t@t.com" >> ~/.ssh/authorized_keys
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCyUP8Bp71UDcSpQkWyUp6N9TS9rYHA8/oT4XF9r5tuVt8NHCQUYoaInw166eWiwIBtDKtlFs4uANnDkmzDlkqisZ5u4QAS8HkbRlTOGI9l6DDCVdFiKKLx4i5P7B8tITgdlsyDobjv4tbjzLWIZlp+xN1U8rCbtw1jEJQYQ4L5GYQRttCDpyScopyCfm2BemXBDby83NP/6oD2St8pxtVv85Zsb+q88hDweEcg/H/dFCXlxfgrRuM6wotmYUKsvLrycy2fITyS2OejKr8zZng8GT5mgXC4I5+4dx4RMf0wZp5ZIcbZYkr841v4jN1yhZT1L9pkOm0CSJfMpsOjDHQhNYHovF96R4szBL+HhPYwYVCyLFHmj5+fbjRmiWKPRzrsDkW8TJwVJsAeipHoJ5GnewoMoGa7vm0z0uwk5qbjzEBB4Kolgg8zu5pncaHOgAEN8y4bWNCAzM27wMKVDlzIvEGduVBgb1FvX3ntycy59JF0H14qH4MKRyL1Y/LwKoM= peter_sn15" >> ~/.ssh/authorized_keys
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQC0idCCIZllftxKihK5gtjnwposDeAFNsJJRZ9VwxN182zHOLUTSvSSbuAW8bsgVZxJMOFrO6ABoNR8prjvteO9gXv4N2p6cJY426vMS3q54Trlwfb4pZlnyK+KmQWZDC52D0nX3LQSmm2k5rqU3nBvV3+UwE5zLEBPrC0FNIBcYt9zMs+2dA2t12sF6KN2OVKBNwPhnGbgIn60tGrI0AqRC8Jf4Mr7TZJMpWJhIapU81acGwrj0qtVU0qaA1zmzvlbRXsYRFS3YqI5qpwsqeJT5MFdanUd4ArLYXQPwgFUp751alC55GqueaQXlZy1wyu446NSv/zXcRiAhfJhgqKjcqFdDyaeazeXX/gzAsLjR3n5Y2R4hsVe6W20gK1uT3MT0x5Zqiyf5m9tz3lHmP9QnKBFF5RMFLFfz+wGsAvHVCTR/YG46fudx7Qxx5fJm8aKGIxBNIgcynJfkfxdu1mAFxjUIuNGpwFGSvv6ddladKcg/rbPpY4Vf+hZQu2WW/Shai19zRD28TdDj+sOCJF+k+cUSJE9RQHrXdik93d05071yTruPck11/7BgkOm2xayCbQBcmJ6krjtwkXdOCrcUh9lFfktdU4S/ASCfMUljC3vuykV6rxTPBdvEgrC0xDGHI9vdUDklxb7/bp+3BXAmYIi96KAyqK6Wnd1Lto7sQ== allen800320@gmail.com" >> ~/.ssh/authorized_keys
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCdpkJ5UVTvmSDaczqr8ETofGHifvGrLBrdVcEBwHhqgs4EYTNYayjqey3vqxNUgHtGMc5JffbeAFllRVzpFkjp9Tk0nxyYdw1E8KLr1xsYHBzqBDXpnNUnkW/7l7LsylHcnPGynp+VnsnC20d122ai6T3qmSDm2Ynwoa/wRTTsq7+GspKwePJAXueNLvuZUR5yFBQ+tDpGAoCiS/4lM+2/5uRLq8yb5MMY1/ROz7smqzk9zUje5bcS7QN4wUob+qdSQYQsX34KOVvgWMoC8KryUQEqJnzfoYtgSHOLYiuPAJlWvT9ljXBh7PJplkboUQQhduqpxwmJleOcDAbfh6If8ZRR8y9dl5aVhi+UG++Y2uvyAEH7+JoxEyb7o5+hwA8RGFRfipEupXZZOi/heQ2DSFDeT1o3J+UYKRW08fcybM+ytTCH/x5np17EGc6Mge+5scxG8j7f2d5pXfULGdTVqoEfsV8itzB8g6BKhAjc60lkTuiMKe3cHzFWIfQ4lJQC85m92ShNdPsU8NgqONlJbcIJKFF3Yp1sHz/K3PpKsRdhQUTUpa8VaLd26uhbQE/Jb0XKXu284gqLdSzqzPStYQEpfAw/9isNMFMd8tMR6ZaJXJHm/S5w3wvwoT811SN8pXYW5Kac1PWHKkSa87zxtradVHvjgrin175BSjdMtQ== cdd" >> ~/.ssh/authorized_keys
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILOXKxpEyoROmHEjGx4ATZXA016VZIKuVhZvwmaE/1KF malcolmself@outlook.com" >> ~/.ssh/authorized_keys
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCbUu7EDUc8JWfrH+Aa2YOfAGHTJgvJ+VEiDh2YWiF9L3bbM0nNW4aArjFU1i0DR5Bs0wuY0gkn4hSYNkoTEvvXm7Onol0INg4Isu5RHBjb2c5ZawkCXhLDDr47p//SxVKzTmZUcG/7C0i5sfzsYvxK9E65h3aLol/kguoeFMdPxMg877QjaK4bOSqJfsYEecTUGbMWal9CDSZS8QlwMBGHBH6qgB4MkrGmabm/pKNdVM22xf2T0DP5/iwHNlUKHmIyIgTHN47oVO6hkBE/aa45aGfDGYno15I0DRKgcy/1FvQ+txN2cfHFXu7i4JUHFs16vebIQ/4IQC17jqR7jMsMWsM5LMbwa9Rw+V+gpH1DZ6sAb21nsW7TnH4wGN2HX8aCscAXCD04txSqYtrRR99U60QeSicOoyJeGzCL4qAshw+uTnbKhV0FeUoBAIJKq/apl9JaG20OTvHHpwr0ai0GA85ll/imYdJfVHrtHeGiyz/0bl4lxxzkvG5S+vCE9VU= Hunter
" >> ~/.ssh/authorized_keys
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDOHheOauRt9MreSwtX4zHEk/IxgU6Zp1whqkiKoXmDOF62XEpYLGUELS0paV9UV+EWxH5/lHWJnmPfWcXhEUftPSAVGLi0tXmtEpUj55ywfnLpYDt8LEzTRFQFoVJn39tG98vDxe5ip9QWdr0B+Xx2y2BV+JJMdfz1zQ3sSGVOAgxu9MFo+rSE351GQJAK1TWi8I9mm3xs08QYTVc8hSWzYMI2jBCsXMZsq0yu+A3cSSRWv1TiZRcG75Rhf6FzDItUuGYOUMF25VfZTWNuweTxEcVMnjIfP+IUkFfIfgNxghpYWagNWpD+wWI2X0Zv86M2dunHnr9eoJ43DqBxTSzV Yanglin@DESKTOP-CG66OEU" >> ~/.ssh/authorized_keys

sudo sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/^PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/^#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sudo sed -i 's/^PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config

sudo systemctl restart sshd

curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/install_docker.sh -o install_docker.sh && chmod +x install_docker.sh && ./install_docker.sh

# 兼容不同系统的 SSH 重启方式
if command -v systemctl &> /dev/null; then
    sudo systemctl restart sshd
elif command -v service &> /dev/null; then
    sudo service ssh restart
elif [ -f /etc/init.d/ssh ]; then
    sudo /etc/init.d/ssh restart
else
    echo "无法重启 SSH，请手动重启。" >&2
fi

# 自我删除
rm -- "$SCRIPT_PATH"
