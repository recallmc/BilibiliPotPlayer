# Launched by launch.bat, which is invoked from the PotPlayer plugin.
# Start-Process derives the new process through the shell, so it does NOT
# inherit the stdout pipe of the caller. This is what keeps
# HostExecuteProgram from blocking forever.
Start-Process -FilePath 'D:\python\pythonw.exe' `
              -ArgumentList 'C:\Users\Recall\bili-proxy\bili_proxy.py' `
              -WindowStyle Hidden
