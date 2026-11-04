@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "runtime\python.exe" (
    start "NewXKY" "runtime\python.exe" "main.py" --hide-console
    exit /b
)
if exist ".venv\Scripts\python.exe" (
    start "NewXKY" ".venv\Scripts\python.exe" "main.py" --hide-console
    exit /b
)
if exist "dist\NewXKY\NewXKY.exe" (
    start "" "dist\NewXKY\NewXKY.exe"
    exit /b
)
echo 请先运行“安装依赖.cmd”，或使用 dist\NewXKY 中的免安装程序。
pause
