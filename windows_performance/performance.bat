@echo off
setlocal enabledelayedexpansion

rem --- Self-elevate to Administrator (UAC) ---
net session >nul 2>&1
if errorlevel 1 (
    echo [INFO] Requesting Administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set SERVICES=DiagTrack WSearch SysMain Spooler PcaSvc

for %%S in (%SERVICES%) do (
    echo.
    echo ===== %%S =====

    sc query %%S | find "STATE" >nul
    if errorlevel 1 (
        echo [SKIP] Service %%S not found
    ) else (
        echo [STOP ] %%S
        sc stop %%S >nul 2>&1

        echo [DISABLE] %%S
        sc config %%S start= disabled >nul 2>&1
    )

    echo [CHECK] sc qc %%S
    sc qc %%S | findstr /i "SERVICE_NAME START_TYPE"
)

echo.
echo Done.
pause
