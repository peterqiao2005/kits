#!/bin/bash
# trojan-go k8s/pod 版一键脚本（无 systemd / 防火墙 / BBR / 包管理）
# 原作者: hijk <https://hijk.art>
# 改造: pod 兼容，前台运行 trojan-go；nginx 后台运行；证书通过挂载或自签；支持环境变量无交互启动。

set -euo pipefail

RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[36m"
PLAIN='\033[0m'

OS="$(hostnamectl 2>/dev/null | grep -i system | cut -d: -f2 || true)"

# IPv4/IPv6 获取
V6_PROXY=""
IP=$(curl -sL -4 ip.sb || true)
if [[ -z "${IP}" ]]; then
    IP=$(curl -sL -6 ip.sb || true)
    V6_PROXY="https://gh.hijk.art/"
fi

NGINX_CONF_PATH="/etc/nginx/conf.d/"
ZIP_FILE="trojan-go"
CONFIG_DIR="/etc/trojan-go"
CONFIG_FILE="${CONFIG_DIR}/config.json"
WS="false"

# 环境变量（优先）——适合 k8s 无交互
# DOMAIN: 必填（如通过 ingress 直连 trojan-go，请确保解析到 Pod/Node/Service）
DOMAIN="${DOMAIN:-}"
PORT="${PORT:-443}"
# 多密码用逗号分隔：PASSWORDS="pass1,pass2"
PASSWORDS="${PASSWORDS:-}"
# WS=true/false
WS="${WS:-false}"
# WSPATH 仅在 WS=true 时有效
WSPATH="${WSPATH:-}"
# PROXY_URL="" 静态站；或 "https://example.com" 做反代
PROXY_URL="${PROXY_URL:-https://bing.imeizi.me}"
# ALLOW_SPIDER=y/n
ALLOW_SPIDER="${ALLOW_SPIDER:-n}"
# TROJAN_GO_VERSION，例如 v0.10.6（可留空自动获取）
TROJAN_GO_VERSION="${TROJAN_GO_VERSION:-}"

colorEcho() {
    echo -e "${1}${*:2}${PLAIN}"
}

status() {
    # 仅检查二进制与配置、及进程
    local trojan_cmd
    trojan_cmd="$(command -v trojan-go || true)"
    if [[ -z "$trojan_cmd" ]]; then
        echo 0; return
    fi
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo 1; return
    fi
    # 端口检测（可选）
    local port
    port="$(cat "$CONFIG_FILE" | grep -E '"local_port"\s*:' | head -n1 | cut -d: -f2 | tr -d \",' ')"
    # 进程检测
    if pgrep -f "trojan-go .*${port}" >/dev/null 2>&1 || pgrep -x trojan-go >/dev/null 2>&1; then
        echo 3
    else
        echo 2
    fi
}

statusText() {
    local s; s="$(status)"
    case "$s" in
        2) echo -e ${GREEN}已安装${PLAIN} ${RED}未运行${PLAIN} ;;
        3) echo -e ${GREEN}已安装${PLAIN} ${GREEN}正在运行${PLAIN} ;;
        *) echo -e ${RED}未安装${PLAIN} ;;
    esac
}

getVersion() {
    if [[ -n "$TROJAN_GO_VERSION" ]]; then
        VERSION="$TROJAN_GO_VERSION"
        [[ ${VERSION:0:1} != "v" ]] && VERSION="v${VERSION}"
        return
    fi
    VERSION="$(curl -fsSL ${V6_PROXY}https://api.github.com/repos/p4gefau1t/trojan-go/releases \
      | grep tag_name | sed -E 's/.*"v(.*)".*/\1/' | head -n1 || true)"
    if [[ -z "$VERSION" ]]; then
        colorEcho $RED "获取 trojan-go 最新版本失败，请设置环境变量 TROJAN_GO_VERSION"
        exit 1
    fi
    [[ ${VERSION:0:1} != "v" ]] && VERSION="v${VERSION}"
}

archAffix() {
    case "${1:-"$(uname -m)"}" in
        i686|i386) echo '386' ;;
        x86_64|amd64) echo 'amd64' ;;
        *armv7*|armv6l) echo 'armv7' ;;
        *armv8*|aarch64) echo 'armv8' ;;
        *armv6*) echo 'armv6' ;;
        *arm*) echo 'arm' ;;
        *mips64le*) echo 'mips64le' ;;
        *mips64*) echo 'mips64' ;;
        *mipsle*) echo 'mipsle-softfloat' ;;
        *mips*) echo 'mips-softfloat' ;;
        *) return 1 ;;
    esac
    return 0
}

# 交互取值（k8s 中通常不用）
getData() {
    echo ""
    local can_change="$1"
    if [[ -z "${DOMAIN}" ]]; then
        echo " trojan-go 一键脚本，请先准备："
        echo -e "  ${RED}1. 一个伪装域名${PLAIN}"
        echo -e "  ${RED}2. 伪装域名DNS解析指向当前服务器/入口（${IP:-unknown}）${PLAIN}"
        echo -e "  3. 如 ${GREEN}/etc/trojan-go/${DOMAIN}.pem${PLAIN} 和 ${GREEN}.key${PLAIN} 已挂载则跳过2"
        read -p " 请输入伪装域名：" DOMAIN
        [[ -z "$DOMAIN" ]] && { colorEcho $RED "伪装域名不能为空"; exit 1; }
    fi
    DOMAIN="${DOMAIN,,}"
    colorEcho $BLUE " 伪装域名(host)：$DOMAIN"

    # 密码
    if [[ -z "$PASSWORDS" ]]; then
        read -p " 请设置 trojan-go 密码（不输则随机）:" pass
        if [[ -z "$pass" ]]; then
            pass="$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 16 | head -n 1)"
        fi
        PASSWORDS="$pass"
        while true; do
            read -p " 是否再设置一组密码？[y/n] " ans
            [[ "${ans,,}" != "y" ]] && break
            read -p " 请输入密码（不输则随机）:" pass2
            [[ -z "$pass2" ]] && pass2="$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 16 | head -n 1)"
            PASSWORDS="${PASSWORDS},${pass2}"
        done
    fi
    colorEcho $BLUE " trojan-go 密码组：$(echo "$PASSWORDS" | sed 's/,/","/g' | sed 's/^/"/;s/$/"/')"

    # 端口
    if [[ -z "${PORT}" ]]; then
        read -p " 请输入 trojan-go 端口[100-65535，默认443]：" PORT
        [[ -z "$PORT" ]] && PORT=443
    fi
    if [[ "${PORT:0:1}" = "0" ]]; then
        colorEcho $RED "端口不能以0开头"; exit 1
    fi
    colorEcho $BLUE " trojan-go 端口：$PORT"

    # WS
    if [[ "${WS}" = "true" ]]; then
        if [[ -z "${WSPATH}" ]]; then
            read -p " 请输入伪装路径（以/开头，留空随机）：" WSPATH
            if [[ -z "$WSPATH" ]]; then
                local len; len=$(shuf -i5-12 -n1)
                local ws;  ws=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w $len | head -n 1)
                WSPATH="/$ws"
            else
                if [[ "${WSPATH:0:1}" != "/" || "${WSPATH}" = "/" ]]; then
                    colorEcho $RED "伪装路径必须以/开头，且不能是根路径/"; exit 1
                fi
            fi
        fi
        colorEcho $BLUE " ws 路径：$WSPATH"
    fi

    # 伪装站
    echo ""
    colorEcho $BLUE " 伪装站点：$PROXY_URL"
    echo ""
    colorEcho $BLUE " 允许搜索引擎：$ALLOW_SPIDER (y/n)"
}

downloadFile() {
    local SUFFIX; SUFFIX="$(archAffix)"
    local DOWNLOAD_URL="${V6_PROXY}https://github.com/p4gefau1t/trojan-go/releases/download/${VERSION}/trojan-go-linux-${SUFFIX}.zip"
    wget -O /tmp/${ZIP_FILE}.zip "$DOWNLOAD_URL"
    [[ -f /tmp/${ZIP_FILE}.zip ]] || { colorEcho $RED "下载 trojan-go 失败"; exit 1; }
}

installTrojan() {
    mkdir -p "$CONFIG_DIR"
    rm -rf /tmp/${ZIP_FILE}
    unzip /tmp/${ZIP_FILE}.zip -d /tmp/${ZIP_FILE}
    cp /tmp/${ZIP_FILE}/trojan-go /usr/bin/
    chmod +x /usr/bin/trojan-go
    rm -rf /tmp/${ZIP_FILE} /tmp/${ZIP_FILE}.zip
    colorEcho $BLUE " trojan-go 安装完成"
}

ensureNginx() {
    if ! command -v nginx >/dev/null 2>&1; then
        colorEcho $RED "容器内未找到 nginx，请基于 nginx 镜像或预装 nginx。"
        exit 1
    fi
}

configNginx() {
    mkdir -p /usr/share/nginx/html
    local ROBOT_CONFIG=""
    if [[ "$ALLOW_SPIDER" = "n" ]]; then
        echo 'User-Agent: *' > /usr/share/nginx/html/robots.txt
        echo 'Disallow: /' >> /usr/share/nginx/html/robots.txt
        ROBOT_CONFIG="    location = /robots.txt {}"
    fi

    # 仅确保主 nginx.conf 包含 conf.d
    if [[ -f /etc/nginx/nginx.conf ]]; then
        grep -q "include /etc/nginx/conf.d/\*\.conf;" /etc/nginx/nginx.conf || true
    fi

    mkdir -p "$NGINX_CONF_PATH"
    if [[ -z "$PROXY_URL" ]]; then
cat > "${NGINX_CONF_PATH}${DOMAIN}.conf" <<-EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    root /usr/share/nginx/html;

    ${ROBOT_CONFIG}
}
EOF
    else
        local REMOTE_HOST; REMOTE_HOST="$(echo "${PROXY_URL}" | cut -d/ -f3)"
cat > "${NGINX_CONF_PATH}${DOMAIN}.conf" <<-EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    root /usr/share/nginx/html;
    location / {
        proxy_ssl_server_name on;
        proxy_pass ${PROXY_URL};
        proxy_set_header Accept-Encoding '';
        sub_filter "${REMOTE_HOST}" "${DOMAIN}";
        sub_filter_once off;
    }
    ${ROBOT_CONFIG}
}
EOF
    fi
}

# 证书处理：优先使用挂载；否则生成自签（测试用）
ensureCert() {
    mkdir -p "$CONFIG_DIR"
    local CERT_FILE="${CONFIG_DIR}/${DOMAIN}.pem"
    local KEY_FILE="${CONFIG_DIR}/${DOMAIN}.key"
    if [[ -f "$CERT_FILE" && -f "$KEY_FILE" ]]; then
        echo "已检测到挂载证书：$CERT_FILE / $KEY_FILE"
        return
    fi
    colorEcho $YELLOW "未检测到挂载证书，使用自签名证书（仅测试用途）"
    if ! command -v openssl >/dev/null 2>&1; then
        colorEcho $RED "容器未安装 openssl，无法自签证书；请挂载有效证书。"
        exit 1
    fi
    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "$KEY_FILE" -out "$CERT_FILE" -days 3650 \
        -subj "/CN=${DOMAIN}"
}

configTrojan() {
    mkdir -p "$CONFIG_DIR"
    local CERT_FILE="${CONFIG_DIR}/${DOMAIN}.pem"
    local KEY_FILE="${CONFIG_DIR}/${DOMAIN}.key"

    # 将 PASSWORDS 转为 JSON 数组
    local pw_json
    pw_json=$(echo "$PASSWORDS" | awk -F, '{
        printf("[");
        for (i=1; i<=NF; i++) {
            gsub(/^[ \t]+|[ \t]+$/, "", $i);
            printf("\"%s\"", $i);
            if (i<NF) printf(",");
        }
        printf("]");
    }')

    # WS 配置片段
    local ws_enabled="false"
    local ws_path=""
    local ws_host="$DOMAIN"
    if [[ "${WS}" = "true" ]]; then
        ws_enabled="true"
        if [[ -z "${WSPATH}" ]]; then
            local len; len=$(shuf -i5-12 -n1)
            local ws;  ws=$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w $len | head -n 1)
            WSPATH="/$ws"
        fi
        ws_path="$WSPATH"
    fi

cat > "$CONFIG_FILE" <<-EOF
{
  "run_type": "server",
  "local_addr": "::",
  "local_port": ${PORT},
  "remote_addr": "127.0.0.1",
  "remote_port": 80,
  "password": ${pw_json},
  "ssl": {
    "cert": "${CERT_FILE}",
    "key": "${KEY_FILE}",
    "sni": "${DOMAIN}",
    "alpn": ["http/1.1"],
    "session_ticket": true,
    "reuse_session": true,
    "fallback_addr": "127.0.0.1",
    "fallback_port": 80
  },
  "tcp": {
    "no_delay": true,
    "keep_alive": true,
    "prefer_ipv4": false
  },
  "mux": {
    "enabled": false,
    "concurrency": 8,
    "idle_timeout": 60
  },
  "websocket": {
    "enabled": ${ws_enabled},
    "path": "${ws_path}",
    "host": "${ws_host}"
  },
  "mysql": {
    "enabled": false,
    "server_addr": "localhost",
    "server_port": 3306,
    "database": "",
    "username": "",
    "password": "",
    "check_rate": 60
  }
}
EOF
}

start_nginx_bg() {
    # 后台启动 nginx（容器内无法使用 systemd）
    # 若主进程是 nginx，应在 K8s 用 sidecar 运行 trojan-go；此处以 trojan-go 为主进程。
    if pgrep -x nginx >/dev/null 2>&1; then
        nginx -s reload || true
    else
        nginx || nginx -g 'daemon off;' &>/var/log/nginx.log &
        sleep 1
    fi
}

start_trojan_fg() {
    # 前台运行 trojan-go（作为容器主进程）
    exec trojan-go -config "$CONFIG_FILE"
}

install() {
    # 交互场景
    getData "no"
    ensureNginx
    ensureCert
    configNginx
    getVersion
    downloadFile
    installTrojan
    configTrojan
    colorEcho $GREEN "安装完成，可执行：$0 run 启动（前台 trojan-go + 后台 nginx）"
}

update() {
    local s; s="$(status)"
    if [[ "$s" -lt 2 ]]; then
        colorEcho $RED "trojan-go 未安装"
        return
    fi
    getVersion
    downloadFile
    installTrojan
    colorEcho $GREEN "trojan-go 已更新到 ${VERSION}"
}

uninstall() {
    local s; s="$(status)"
    if [[ "$s" -lt 2 ]]; then
        colorEcho $RED "trojan-go 未安装"
        return
    fi
    local domain
    domain="$(cat "$CONFIG_FILE" | grep -E '"sni"\s*:' | head -n1 | cut -d\" -f4)"
    pkill -x trojan-go || true
    rm -f /usr/bin/trojan-go
    rm -rf "$CONFIG_DIR"
    rm -f "${NGINX_CONF_PATH}${domain}.conf" || true
    colorEcho $GREEN "卸载完成（未删除 nginx 程序本体）"
}

start() {
    local s; s="$(status)"
    if [[ "$s" -lt 2 ]]; then
        colorEcho $RED "trojan-go 未安装或未配置"; return
    fi
    ensureNginx
    start_nginx_bg
    # 后台 trojan-go（兼容旧逻辑），新版 run 使用前台
    trojan-go -config "$CONFIG_FILE" &>/var/log/trojan-go.log &
    sleep 2
    if pgrep -x trojan-go >/dev/null 2>&1; then
        colorEcho $BLUE " trojan-go 启动成功"
    else
        colorEcho $RED " trojan-go 启动失败，请检查端口占用或配置"
    fi
}

stop() {
    pkill -x trojan-go || true
    # 不强停 nginx，避免影响同容器其它站点；如需停止：
    # pkill -x nginx || true
    colorEcho $BLUE " trojan-go 已停止"
}

restart() {
    stop
    start
}

reconfig() {
    local s; s="$(status)"
    if [[ "$s" -lt 2 ]]; then
        colorEcho $RED "trojan-go 未安装"; return
    fi
    # 交互重配（k8s 下建议通过 env 直接覆盖）
    getData "yes"
    ensureNginx
    ensureCert
    configNginx
    configTrojan
    restart
    showInfo
}

showInfo() {
    local s; s="$(status)"
    if [[ "$s" -lt 2 ]]; then
        colorEcho $RED "trojan-go 未安装"; return
    fi
    local domain port ws
    domain="$(cat "$CONFIG_FILE" | grep -E '"sni"\s*:' | head -n1 | cut -d\" -f4)"
    port="$(cat "$CONFIG_FILE" | grep -E '"local_port"\s*:' | head -n1 | cut -d: -f2 | tr -d \",' ')"
    ws="$(cat "$CONFIG_FILE" | grep -n 'websocket' -n | head -n1 | cut -d: -f1 | xargs -I{} sed -n "$(({}+1))p" "$CONFIG_FILE" | cut -d: -f2 | tr -d \",' ')"
    local password_line
    password_line="$(cat "$CONFIG_FILE" | grep -n '"password"' | head -n1 | cut -d: -f1)"
    local password_show
    password_show="$(sed -n "$((password_line+1))p" "$CONFIG_FILE" | tr -d ' []",')"
    echo ""
    echo -n " trojan-go 运行状态："; statusText
    echo ""
    echo -e " ${BLUE}配置文件: ${PLAIN} ${RED}${CONFIG_FILE}${PLAIN}"
    echo -e " ${BLUE}配置信息：${PLAIN}"
    echo -e "   IP：${RED}${IP:-unknown}${PLAIN}"
    echo -e "   域名/SNI：${RED}$domain${PLAIN}"
    echo -e "   端口：${RED}$port${PLAIN}"
    echo -e "   密码(去引号去数组展示)：${RED}$password_show${PLAIN}"
    if [[ "$ws" = "true" ]]; then
        local wspath
        wspath="$(cat "$CONFIG_FILE" | grep -E '"path"\s*:' | head -n1 | cut -d: -f2 | tr -d \",' ')"
        echo -e "   websocket：${RED}true${PLAIN}"
        echo -e "   ws 路径：${RED}${wspath}${PLAIN}"
    fi
    echo ""
}

showLog() {
    # 容器中没 journald，直接 cat 日志文件或输出进程日志
    if [[ -f /var/log/trojan-go.log ]]; then
        tail -n 200 /var/log/trojan-go.log
    else
        pgrep -a trojan-go || true
        echo "未找到 /var/log/trojan-go.log，可查看容器 stdout/stderr"
    fi
}

run() {
    # 非交互、以 env 驱动的“一条龙”启动（适用于 K8s 容器主进程）
    [[ -z "${DOMAIN}" ]] && { colorEcho $RED "环境变量 DOMAIN 未设置"; exit 1; }
    [[ -z "${PASSWORDS}" ]] && PASSWORDS="$(cat /dev/urandom | tr -dc 'a-zA-Z0-9' | fold -w 16 | head -n 1)"
    ensureNginx
    ensureCert
    configNginx
    getVersion
    # 若二进制不存在则下载
    if ! command -v trojan-go >/dev/null 2>&1; then
        downloadFile
        installTrojan
    fi
    configTrojan

    # 先启动 nginx（后台），再以前台模式运行 trojan-go 作为容器主进程
    start_nginx_bg
    echo "启动 trojan-go（前台）..."
    start_trojan_fg
}

menu() {
    clear
    echo "#############################################################"
    echo -e "#           ${RED}trojan-go（k8s/pod版）一键脚本${PLAIN}                 #"
    echo "#############################################################"
    echo ""
    echo -e "  ${GREEN}1.${PLAIN}  安装 trojan-go（交互）"
    echo -e "  ${GREEN}2.${PLAIN}  更新 trojan-go"
    echo -e "  ${GREEN}3.  ${RED}卸载 trojan-go${PLAIN}"
    echo " -------------"
    echo -e "  ${GREEN}4.${PLAIN}  启动（后台）"
    echo -e "  ${GREEN}5.${PLAIN}  重启（后台）"
    echo -e "  ${GREEN}6.${PLAIN}  停止（后台）"
    echo " -------------"
    echo -e "  ${GREEN}7.${PLAIN}  查看配置"
    echo -e "  ${GREEN}8.${PLAIN}  查看日志"
    echo " -------------"
    echo -e "  ${GREEN}9.${PLAIN}  交互修改配置"
    echo -e "  ${GREEN}10.${PLAIN} 前台运行（适用于容器主进程）"
    echo -e "  ${GREEN}0.${PLAIN}  退出"
    echo
    echo -n " 当前状态："; statusText
    echo
    read -p " 请选择操作[0-10]：" answer
    case "$answer" in
        0) exit 0 ;;
        1) install ;;
        2) update ;;
        3) uninstall ;;
        4) start ;;
        5) restart ;;
        6) stop ;;
        7) showInfo ;;
        8) showLog ;;
        9) reconfig ;;
        10) run ;;
        *) echo -e "$RED 请选择正确的操作！${PLAIN}"; exit 1 ;;
    esac
}

# ===== 主流程 =====
action="${1:-menu}"
case "$action" in
    menu|install|update|uninstall|start|restart|stop|showInfo|showLog|reconfig|run)
        ${action}
        ;;
    *)
        echo " 参数错误"
        echo " 用法: $(basename "$0") [menu|install|update|uninstall|start|restart|stop|showInfo|showLog|reconfig|run]"
        exit 1
        ;;
esac
