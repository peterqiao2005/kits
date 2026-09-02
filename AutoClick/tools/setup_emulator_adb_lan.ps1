# =====================================================================
#  The Tower · 模拟器 ADB 局域网远程共享一键配置工具 (PowerShell 版)
# =====================================================================

# 1. 确保以管理员权限运行
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "正在请求管理员权限，请在弹出的 UAC 窗口中点击【是】..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

function Show-Menu {
    Clear-Host
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host "      The Tower · 模拟器 ADB 局域网远程共享一键配置工具" -ForegroundColor Green
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host " 本工具用于在【运行模拟器的电脑】上，将仅监听 127.0.0.1 的 ADB 端口"
    Write-Host " 转发到所有局域网网卡 (0.0.0.0)，并自动配置 Windows 防火墙入站规则。"
    Write-Host ""
    Write-Host " [1] 添加 / 更新 ADB 端口转发与防火墙规则 (推荐)" -ForegroundColor White
    Write-Host " [2] 查看当前已配置的所有端口转发规则" -ForegroundColor White
    Write-Host " [3] 删除指定端口的转发规则与防火墙规则" -ForegroundColor White
    Write-Host " [4] 退出" -ForegroundColor White
    Write-Host ""
    Write-Host "=====================================================================" -ForegroundColor Cyan
    $choice = Read-Host "请输入选项序号 [1-4] (默认 1)"
    if ([string]::IsNullOrWhiteSpace($choice)) { $choice = "1" }

    switch ($choice) {
        "1" { Add-ForwardRule }
        "2" { View-ForwardRules }
        "3" { Remove-ForwardRule }
        "4" { exit }
        default { Show-Menu }
    }
}

function Add-ForwardRule {
    Clear-Host
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host "              【步骤 1/2】请输入模拟器的 ADB 端口" -ForegroundColor Green
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host " 常见模拟器默认端口参考:"
    Write-Host "  - BlueStacks (主实例): 5555"
    Write-Host "  - BlueStacks (多开/随机端口): 5565, 5575, 65334 等 (请在设置中查看)"
    Write-Host "  - 雷电模拟器 (LDPlayer): 5555 (多开: 5555+序号*2)"
    Write-Host "  - MuMu 模拟器: 7555 / 16384 等"
    Write-Host ""
    
    $portStr = Read-Host "请输入您要开放转发的 ADB 端口号 (如 5575)"
    if ([string]::IsNullOrWhiteSpace($portStr) -or -not ($portStr -match '^\d+$')) {
        Write-Host "`n[错误] 请输入有效的数字端口号！" -ForegroundColor Red
        Pause
        Show-Menu
        return
    }

    $port = [int]$portStr

    Write-Host "`n[1/2] 正在配置 Windows 底层端口转发 (0.0.0.0:$port -> 127.0.0.1:$port)..." -ForegroundColor Yellow
    netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$port 2>$null | Out-Null
    netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$port connectaddress=127.0.0.1 connectport=$port

    Write-Host "[2/2] 正在配置 Windows 防火墙放行 TCP 端口 $port..." -ForegroundColor Yellow
    Remove-NetFirewallRule -DisplayName "TheTower_ADB_$port" -ErrorAction SilentlyContinue 2>$null | Out-Null
    New-NetFirewallRule -DisplayName "TheTower_ADB_$port" -Direction Inbound -LocalPort $port -Protocol TCP -Action Allow -ErrorAction SilentlyContinue | Out-Null

    Write-Host ""
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host "                    🎉 配置完成！连接信息如下" -ForegroundColor Green
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host " 本机在局域网中的可用 IP 建议填入:" -ForegroundColor White
    $ips = Get-NetIPAddress -AddressFamily IPv4 -Type Unicast | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" }
    foreach ($ip in $ips) {
        Write-Host "   👉 $($ip.IPAddress):$port" -ForegroundColor Yellow -NoNewline
        Write-Host "  (接口: $($ip.InterfaceAlias))" -ForegroundColor Gray
    }
    Write-Host ""
    Write-Host " 在另一台电脑的 Web 页面中：" -ForegroundColor White
    Write-Host " 1. 账户管理中填写 ADB 设备为上面黄色高亮的 IP:端口"
    Write-Host " 2. 点击【🚀 ADB 快速导入】即可全自动跨机器同步存档！"
    Write-Host ""
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Pause
    Show-Menu
}

function View-ForwardRules {
    Clear-Host
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host "                    当前系统所有 IPv4 端口转发规则" -ForegroundColor Green
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host ""
    netsh interface portproxy show v4tov4
    Write-Host ""
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Pause
    Show-Menu
}

function Remove-ForwardRule {
    Clear-Host
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host "                    删除指定端口的转发规则" -ForegroundColor Red
    Write-Host "=====================================================================" -ForegroundColor Cyan
    Write-Host ""
    $portStr = Read-Host "请输入要删除的端口号"
    if (-not [string]::IsNullOrWhiteSpace($portStr) -and ($portStr -match '^\d+$')) {
        $port = [int]$portStr
        netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$port 2>$null | Out-Null
        Remove-NetFirewallRule -DisplayName "TheTower_ADB_$port" -ErrorAction SilentlyContinue 2>$null | Out-Null
        Write-Host "`n[成功] 已删除端口 $port 的转发与防火墙规则。" -ForegroundColor Green
    }
    Write-Host ""
    Pause
    Show-Menu
}

# 启动主菜单
Show-Menu
