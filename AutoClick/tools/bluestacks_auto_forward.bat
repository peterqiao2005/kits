@echo off
setlocal
chcp 65001 >nul
title BlueStacks 5 动态端口自动映射为【固定局域网端口】工具

:: 1. 检查并自动提升管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在请求管理员权限，请在弹出的 UAC 窗口中点击【是】...
    powershell -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

:: 2. 如果同目录下存在 ps1 文件，直接执行
if exist "%~dp0bluestacks_auto_forward.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bluestacks_auto_forward.ps1"
    exit /b
)

:: 3. 兼容单独拷贝 bat 的情况：直接调用 PowerShell
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$confPath = 'C:\ProgramData\BlueStacks_nxt\bluestacks.conf';" ^
"if (-not (Test-Path $confPath)) { Write-Host '[错误] 未找到 BlueStacks 配置文件: ' $confPath -ForegroundColor Red; Pause; exit 1; }" ^
"$bs = Get-Process -Name 'HD-Player' -ErrorAction SilentlyContinue;" ^
"if (-not $bs) { Write-Host '[警告] 未检测到运行中的 BlueStacks (HD-Player) 进程，请先启动模拟器！' -ForegroundColor Red; Pause; exit 1; }" ^
"$lines = Get-Content $confPath; $instances = @{};" ^
"foreach ($line in $lines) {" ^
"    if ($line -match 'bst\.instance\.([^\.]+)\.display_name=\x22([^\x22]+)\x22') { $id = $matches[1]; if (-not $instances[$id]) { $instances[$id] = @{} }; $instances[$id].Name = $matches[2]; }" ^
"    if ($line -match 'bst\.instance\.([^\.]+)\.status\.adb_port=\x22(\d+)\x22') { $id = $matches[1]; if (-not $instances[$id]) { $instances[$id] = @{} }; $instances[$id].Port = $matches[2]; }" ^
"}" ^
"$active = $instances.GetEnumerator() | Where-Object { $_.Value.Port -and $_.Value.Port -ne '0' };" ^
"if ($active.Count -eq 0) { Write-Host '[警告] 未检测到开启 ADB 调试的实例，请在设置中开启 ADB！' -ForegroundColor Red; Pause; exit 1; }" ^
"$fixed = @(5555, 5565, 5575, 5585, 5595, 5605);" ^
"$ip = (Get-NetIPAddress -AddressFamily IPv4 -Type Unicast | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress;" ^
"$idx = 0; $summary = @();" ^
"foreach ($inst in $active) {" ^
"    $fp = $fixed[$idx]; $dp = $inst.Value.Port; $nm = if ($inst.Value.Name) { $inst.Value.Name } else { $inst.Key };" ^
"    netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$fp 2>$null | Out-Null;" ^
"    netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$fp connectaddress=127.0.0.1 connectport=$dp | Out-Null;" ^
"    Remove-NetFirewallRule -DisplayName ('TheTower_ADB_' + $fp) -ErrorAction SilentlyContinue 2>$null | Out-Null;" ^
"    New-NetFirewallRule -DisplayName ('TheTower_ADB_' + $fp) -Direction Inbound -LocalPort $fp -Protocol TCP -Action Allow -ErrorAction SilentlyContinue 2>$null | Out-Null;" ^
"    $summary += [PSCustomObject]@{ '实例名称' = $nm; 'BlueStacks动态端口' = $dp; '固定局域网连接地址 (Web端填这个)' = ($ip + ':' + $fp) };" ^
"    $idx++;" ^
"}" ^
"Write-Host '=====================================================================' -ForegroundColor Cyan;" ^
"$summary | Format-Table -AutoSize | Out-String | Write-Host -ForegroundColor Yellow;" ^
"Write-Host '=====================================================================' -ForegroundColor Cyan;" ^
"Write-Host '🎉 端口映射已就绪！Web 端直接填写上述固定地址即可。' -ForegroundColor Green; Pause;"
