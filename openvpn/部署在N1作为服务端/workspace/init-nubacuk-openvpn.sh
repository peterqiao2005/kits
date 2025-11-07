docker run --name ovpn-gen -v $PWD/ovpn-data:/etc/openvpn --rm \
  nubacuk/docker-openvpn:aarch64 \
  ovpn_genconfig -u tcp://vpn-shanghai.3518.pro:11443

docker run --name ovpn-init -v $PWD/ovpn-data:/etc/openvpn --rm -it \
  nubacuk/docker-openvpn:aarch64 easyrsa build-server-full server nopass

docker run --name ovpn-init2 -v $PWD/ovpn-data:/etc/openvpn --rm -it \
  nubacuk/docker-openvpn:aarch64 ovpn_initpki nopass

