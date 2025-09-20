sudo apt update
sudo apt install openvpn -y
sudo mkdir -p /etc/openvpn/client
sudo cp ./vpn-johor.ovpn /etc/openvpn/client/vpn-johor.conf
sudo chmod 600 /etc/openvpn/client/vpn-johor.conf
sudo chown root:root /etc/openvpn/client/vpn-johor.conf

sudo systemctl enable openvpn-client@vpn-johor
sudo systemctl start  openvpn-client@vpn-johor

systemctl status openvpn-client@vpn-johor
# tail -f /var/log/syslog | grep openvpn