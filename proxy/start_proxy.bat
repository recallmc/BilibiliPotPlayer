@echo off
setlocal
cd /d "%~dp0"

set PORT=18999

rem ---- Prefer pythonw (no console window); fall back to python ----
set PYW=pythonw
where pythonw >nul 2>&1
if errorlevel 1 set PYW=python

rem ---- Check whether an instance is already listening ----
%PYW% -c "import socket,sys;s=socket.socket();r=s.connect_ex(('127.0.0.1',%PORT%));s.close();sys.exit(0 if r==0 else 1)" >nul 2>&1
if not errorlevel 1 (
    echo.
    echo   [OK] Proxy is already running on port %PORT%.
    echo        No need to start it again.
    echo.
    timeout /t 3 >nul
    exit /b
)

rem ---- Start ----
start "" %PYW% "%~dp0bili_proxy.py"

echo.
echo   [OK] Bilibili proxy started on port %PORT%.
echo        It will exit automatically about 25s after PotPlayer closes.
echo.
echo        Test:  http://127.0.0.1:%PORT%/ping
echo.
timeout /t 3 >nul
