@echo off
rem Called by the PotPlayer plugin from OnInitialize via cmd /c
rem
rem Do NOT start pythonw directly here. If the child process inherits this
rem script's stdout pipe, HostExecuteProgram waits for that pipe to reach EOF
rem and the player freezes ("Not Responding").
rem
rem Start-Process derives the process through the shell, which detaches it
rem from the inherited pipe, so the caller returns immediately.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1"
exit /b 0
