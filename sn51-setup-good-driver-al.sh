#!/bin/bash

# 获取当前脚本的绝对路径
SCRIPT_PATH=$(readlink -f "$0")

apt-get update

apt install ufw url sudo -y

sudo ufw allow 22
sudo ufw allow 3000:40000/tcp

echo "y" | sudo ufw enable

sudo ufw status

rm -rf ~/.ssh/authorized_keys

echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCyUP8Bp71UDcSpQkWyUp6N9TS9rYHA8/oT4XF9r5tuVt8NHCQUYoaInw166eWiwIBtDKtlFs4uANnDkmzDlkqisZ5u4QAS8HkbRlTOGI9l6DDCVdFiKKLx4i5P7B8tITgdlsyDobjv4tbjzLWIZlp+xN1U8rCbtw1jEJQYQ4L5GYQRttCDpyScopyCfm2BemXBDby83NP/6oD2St8pxtVv85Zsb+q88hDweEcg/H/dFCXlxfgrRuM6wotmYUKsvLrycy2fITyS2OejKr8zZng8GT5mgXC4I5+4dx4RMf0wZp5ZIcbZYkr841v4jN1yhZT1L9pkOm0CSJfMpsOjDHQhNYHovF96R4szBL+HhPYwYVCyLFHmj5+fbjRmiWKPRzrsDkW8TJwVJsAeipHoJ5GnewoMoGa7vm0z0uwk5qbjzEBB4Kolgg8zu5pncaHOgAEN8y4bWNCAzM27wMKVDlzIvEGduVBgb1FvX3ntycy59JF0H14qH4MKRyL1Y/LwKoM= peter_sn15" >> ~/.ssh/authorized_keys
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDSPUgoMPLaoxk1J4VLfrzvLBuC1gD0NyktZG5ei4hXJaZtW0iRS1X3pETIohICTawTdGMC5L1R2lFMzIqjae1/4ZOOmyc8Uy4nJyfQfffsNTdWLrJ5O7HR1F94jvfasLgXqEnCuUTMBvURuMkqHmnxmLaLLocaYE4ykscoDNMiUixB+KHHNM7i23PrWnQ/mve7s/R5nwNkb5XiegeUxZoALu0LsptMJ82JHdRdDE/GeCo8OnXK6fDZWxKzsh61KosyXcYmLbGtiimV3piAgXS/1LsgIRFtvbpgJx6tDRfVGFHR3Lo3VVAGAXMV8FgrpMBH22yuOiQiQHp4BuyInvAvBwfzEkz+srqe51rGlh5jrP6OnRUCAeY2WJmIehuhIwsBqL8zwXSY8LSzRb9pDZI3dDMBmGVMi7vDfzUbrHd4PZz2yz+sY99B1/M8x4JWJqPDOE4woGPoo0M747Jf0VJ620DEKWp0y4nn8wJFVi6xwLDIlDkRRcdRToru1S9Z0kM= austinlauncher_RSA" >> ~/.ssh/authorized_keys
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHYoJA6lAqxlsk2oLDCX4fHnSYAg5cgUZjqEKNLChnWh liyuanyou" >> ~/.ssh/authorized_keys
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIKkYMOil23nJ/AdUYcLksj1rdrRDv8Sk41+V/pr1f2dH austinlauncher@sn51" >> ~/.ssh/authorized_keys





sudo sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/^PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config

sudo systemctl restart sshd

nvidia-smi -pm 1

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update

sudo apt install -y nvidia-container-runtime nvidia-container-toolkit

curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/install_docker.sh -o install_docker.sh && chmod +x install_docker.sh && ./install_docker.sh

echo '{
  "default-runtime": "nvidia",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}' | sudo tee /etc/docker/daemon.json > /dev/null

systemctl restart docker

cd ~
mkdir -p ~/workspace/sn51/
cd ~/workspace/sn51/

git clone https://github.com/Datura-ai/compute-subnet.git
cd compute-subnet && chmod +x scripts/install_executor_on_ubuntu.sh && scripts/install_executor_on_ubuntu.sh

cd ~/workspace/sn51/compute-subnet/neurons/executor
curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/executor_al/docker-compose.app.yml -o docker-compose.app.yml
curl -fsSL https://raw.githubusercontent.com/peterqiao2005/kits/main/executor_al/.env -o .env

docker compose -f docker-compose.app.yml up -d

# 自我删除
rm -- "$SCRIPT_PATH"
