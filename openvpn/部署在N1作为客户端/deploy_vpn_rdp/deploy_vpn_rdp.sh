sudo bash setup_armbian_vpn_rdp.sh \
  RDP_USER='ai' \
  RDP_PASS='32167' \
  RDP_HOST='192.168.100.108' \
  OVPN_FILE='/root/client.ovpn' \
  OVPN_NAME='vpn-jb' \
  LOCAL_USER='root' \
  RDP_FULL=1
