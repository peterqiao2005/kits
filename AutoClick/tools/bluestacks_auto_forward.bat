@echo off
chcp 65001 >nul
title BlueStacks 5 动态端口自动映射为【固定局域网端口】工具

:: 1. 优先使用 Python 原生执行 (100% 避免 PowerShell 编码与字符集问题)
where python >nul 2>&1
if %errorlevel% equ 0 (
    if exist "%~dp0bluestacks_auto_forward.py" (
        python "%~dp0bluestacks_auto_forward.py"
        exit /b
    )
)

:: 2. 如果没有 Python，则运行 PowerShell 脚本
if exist "%~dp0bluestacks_auto_forward.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bluestacks_auto_forward.ps1"
    exit /b
)

echo [错误] 未找到 bluestacks_auto_forward.py 或 bluestacks_auto_forward.ps1 脚本文件。
pause
