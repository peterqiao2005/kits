# =====================================================================
#  The Tower · BlueStacks 实例端口全自动侦测与固定映射工具 (PowerShell 版)
# =====================================================================

# 1. 确保以管理员权限运行
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[提示] 正在请求管理员权限，请在弹出的 UAC 窗口中点击【是】..." -ForegroundColor Yellow
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Clear-Host
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "   The Tower · BlueStacks 实例端口全自动侦测与固定映射工具" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[1/3] 正在扫描 BlueStacks 5 配置文件与所有运行中实例..." -ForegroundColor Yellow

# 检查 BlueStacks 进程是否正在运行
$bsProcesses = Get-Process -Name "HD-Player" -ErrorAction SilentlyContinue
if (-not $bsProcesses) {
    Write-Host "`n[警告] 当前系统中未检测到任何正在运行的 BlueStacks (HD-Player.exe) 进程！" -ForegroundColor Red
    Write-Host "👉 原因排查:" -ForegroundColor Yellow
    Write-Host "   1. 模拟器尚未启动或在后台崩溃退出；" -ForegroundColor White
    Write-Host "   2. 请在桌面上打开 BlueStacks 多开管理器，并【启动】您的模拟器实例；" -ForegroundColor White
    Write-Host "   3. 确保模拟器窗口已经完全进入 Android 系统桌面并已开启游戏。" -ForegroundColor White
    Write-Host ""
    Pause
    exit 1
}

$confPath = 'C:\ProgramData\BlueStacks_nxt\bluestacks.conf'
if (-not (Test-Path $confPath)) {
    Write-Host "`n[错误] 未找到 BlueStacks 配置文件: $confPath" -ForegroundColor Red
    Write-Host "请确认该机器已正确安装 BlueStacks 5。" -ForegroundColor Yellow
    Pause
    exit 1
}

$lines = Get-Content $confPath
$instances = @{}
foreach ($line in $lines) {
    if ($line -match 'bst\.instance\.([^\.]+)\.display_name="([^"]+)"') {
        $id = $matches[1]
        if (-not $instances[$id]) { $instances[$id] = @{} }
        $instances[$id].Name = $matches[2]
    }
    if ($line -match 'bst\.instance\.([^\.]+)\.status\.adb_port="(\d+)"') {
        $id = $matches[1]
        if (-not $instances[$id]) { $instances[$id] = @{} }
        $instances[$id].Port = $matches[2]
    }
}

$activeInstances = $instances.GetEnumerator() | Where-Object { $_.Value.Port -and $_.Value.Port -ne '0' }
if ($activeInstances.Count -eq 0) {
    Write-Host "`n[警告] 虽有模拟器进程，但未检测到任何开放 ADB 端口的实例。" -ForegroundColor Red
    Write-Host "👉 解决方法:" -ForegroundColor Yellow
    Write-Host "   1. 打开 BlueStacks 窗口右下角【设置 (齿轮图标)】；" -ForegroundColor White
    Write-Host "   2. 切换到【高级 (Advanced)】选项卡；" -ForegroundColor White
    Write-Host "   3. 找到【Android 调试桥 (ADB)】，将其开关打开并保存更改；" -ForegroundColor White
    Write-Host "   4. 重启模拟器后再次运行本工具！" -ForegroundColor White
    Write-Host ""
    Pause
    exit 1
}

Write-Host "[2/3] 正在建立固定端口转发 (5555, 5565, 5575...)..." -ForegroundColor Cyan
$fixedPorts = @(5555, 5565, 5575, 5585, 5595, 5605)
$ip = (Get-NetIPAddress -AddressFamily IPv4 -Type Unicast | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress

$idx = 0
$summary = @()
foreach ($inst in $activeInstances) {
    $fixPort = $fixedPorts[$idx]
    $dynPort = $inst.Value.Port
    $name = if ($inst.Value.Name) { $inst.Value.Name } else { $inst.Key }

    # 1. 端口转发: 0.0.0.0:固定端口 -> 127.0.0.1:BlueStacks当前动态端口
    netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$fixPort 2>$null | Out-Null
    netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$fixPort connectaddress=127.0.0.1 connectport=$dynPort | Out-Null

    # 2. 防火墙放行固定端口
    Remove-NetFirewallRule -DisplayName "TheTower_ADB_$fixPort" -ErrorAction SilentlyContinue 2>$null | Out-Null
    New-NetFirewallRule -DisplayName "TheTower_ADB_$fixPort" -Direction Inbound -LocalPort $fixPort -Protocol TCP -Action Allow -ErrorAction SilentlyContinue 2>$null | Out-Null

    $summary += [PSCustomObject]@{
        '实例名称' = $name
        'BlueStacks当前动态端口' = $dynPort
        '固定局域网连接地址 (Web端填这个)' = "$ip`:$fixPort"
    }
    $idx++
}

Write-Host "[3/3] 配置完成！当前映射关系如下:" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
$summary | Format-Table -AutoSize | Out-String | Write-Host -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "🎉 以后在 Web 端【多账户管理】中，直接填写上面的【固定局域网连接地址】即可！" -ForegroundColor Green
Write-Host "即使 BlueStacks 重启变了内部端口，只需再双击运行一次本脚本，端口映射即刻自动重连，Web 端配置永久无需修改！" -ForegroundColor White
Write-Host ""
Pause
