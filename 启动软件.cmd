@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "NewXKY" ".venv\Scripts\pythonw.exe" "main.py" --hide-console
    exit /b
)
if exist "dist\release\NewXKY\NewXKY.exe" (
    start "" "dist\release\NewXKY\NewXKY.exe"
    exit /b
)
if exist "dist\NewXKY\NewXKY.exe" (
    start "" "dist\NewXKY\NewXKY.exe"
    exit /b
)
if exist "runtime\pythonw.exe" (
    start "NewXKY" "runtime\pythonw.exe" "main.py" --hide-console
    exit /b
)
echo 请先运行“安装依赖.cmd”，或解压并运行 dist\NewXKY\NewXKY.exe。
pause
