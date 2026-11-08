@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto failed
echo 安装完成，请运行“启动软件.cmd”。
pause
exit /b 0
:failed
echo 安装失败，请确认已安装 Python 3.11 或 3.12，并检查网络连接。
pause
exit /b 1
