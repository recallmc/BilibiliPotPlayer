@echo off
rem ============================================================
rem  Called by the PotPlayer plugin from OnInitialize via "cmd /c"
rem  Launches the local CDN proxy in background (no console window)
rem
rem  If pythonw.exe is not in your PATH, replace the line below with
rem  the full path, for example:
rem      set PYTHONW=D:\python\pythonw.exe
rem ============================================================

set PYTHONW=pythonw
set PROXYSCRIPT=%~dp0bili_proxy.py

start "" %PYTHONW% "%PROXYSCRIPT%"
