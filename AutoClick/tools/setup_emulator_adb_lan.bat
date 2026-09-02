@echo off
chcp 65001 >nul
title BlueStacks / 安卓模拟器 ADB 局域网跨机器共享配置工具

:: 1. 管理员权限自动提升检测
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在请求管理员权限，请在弹出的 UAC 窗口中点击【是】...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

:MENU
cls
echo =====================================================================
echo       The Tower · 模拟器 ADB 局域网远程共享一键配置工具
echo =====================================================================
echo.
echo  本工具用于在【运行模拟器的电脑】上，将仅监听 127.0.0.1 的 ADB 端口
echo  转发到所有局域网网卡 (0.0.0.0)，并自动配置 Windows 防火墙入站规则。
echo.
echo  [1] 添加 / 更新 ADB 端口转发与防火墙规则 (推荐)
echo  [2] 查看当前已配置的所有端口转发规则
echo  [3] 删除指定端口的转发规则与防火墙规则
echo  [4] 退出
echo.
echo =====================================================================
set /p CHOICE="请输入选项序号 [1-4] (默认 1): "
if "%CHOICE%"=="" set CHOICE=1
if "%CHOICE%"=="1" goto ADD_RULE
if "%CHOICE%"=="2" goto SHOW_RULES
if "%CHOICE%"=="3" goto DEL_RULE
if "%CHOICE%"=="4" exit /b
goto MENU

:ADD_RULE
cls
echo =====================================================================
echo               【步骤 1/2】请输入模拟器的 ADB 端口
echo =====================================================================
echo.
echo  常见模拟器默认端口参考:
echo   - BlueStacks (主实例): 5555
echo   - BlueStacks (多开/随机端口): 5565, 5575, 65334 等 (请在设置中查看)
echo   - 雷电模拟器 (LDPlayer): 5555 (多开: 5555+序号*2，如 5557)
echo   - MuMu 模拟器: 7555 / 16384 等
echo.
set /p PORT="请输入您要开放转发的 ADB 端口号 (如 5575): "

if "%PORT%"=="" (
    echo.
    echo [错误] 端口号不能为空，按任意键重试...
    pause >nul
    goto ADD_RULE
)

:: 校验端口是否全为纯数字
for /f "delims=0123456789" %%i in ("%PORT%") do (
    echo.
    echo [错误] 端口号必须全为数字: %PORT%
    pause >nul
    goto ADD_RULE
)

echo.
echo [1/2] 正在配置 Windows 底层端口转发 (0.0.0.0:%PORT% -> 127.0.0.1:%PORT%)...
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=%PORT% >nul 2>&1
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=%PORT% connectaddress=127.0.0.1 connectport=%PORT%

if %errorlevel% neq 0 (
    echo [失败] netsh 端口转发配置异常，请检查是否有冲突。
) else (
    echo [成功] netsh 端口转发已建立！
)

echo.
echo [2/2] 正在配置 Windows 防火墙放行 TCP 端口 %PORT%...
netsh advfirewall firewall delete rule name="TheTower_ADB_%PORT%" >nul 2>&1
netsh advfirewall firewall add rule name="TheTower_ADB_%PORT%" dir=in action=allow protocol=TCP localport=%PORT% >nul

if %errorlevel% neq 0 (
    echo [警告] 防火墙规则创建异常，请手动确认防火墙状态。
) else (
    echo [成功] 防火墙已允许 TCP 端口 %PORT% 入站！
)

echo.
echo =====================================================================
echo                     🎉 配置完成！连接信息如下
echo =====================================================================
echo.
echo  本机在局域网中的 IP 地址为:
for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 -Type Unicast | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' }).IPAddress"`) do (
    echo    👉 %%a:%PORT%
)
echo.
echo  在另一台电脑的 Web 页面中：
echo  1. 账户管理中填写 ADB 设备为: [上述IP]:%PORT% (如 192.168.1.219:%PORT%)
echo  2. 点击【🚀 ADB 快速导入】即可全自动跨机器同步存档！
echo.
echo =====================================================================
pause
goto MENU

:SHOW_RULES
cls
echo =====================================================================
echo                     当前系统所有 IPv4 端口转发规则
echo =====================================================================
echo.
netsh interface portproxy show v4tov4
echo.
echo =====================================================================
pause
goto MENU

:DEL_RULE
cls
echo =====================================================================
echo                     删除指定端口的转发规则
echo =====================================================================
echo.
set /p DEL_PORT="请输入要删除的端口号: "
if "%DEL_PORT%"=="" goto MENU

netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=%DEL_PORT% >nul 2>&1
netsh advfirewall firewall delete rule name="TheTower_ADB_%DEL_PORT%" >nul 2>&1

echo.
echo [成功] 已删除端口 %DEL_PORT% 的转发与防火墙规则。
echo.
pause
goto MENU
