@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "dist\ShiYing\拾影.exe" (
  start "" "dist\ShiYing\拾影.exe"
  exit /b
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "main.py"
  exit /b
)
echo 请先解压完整的应用文件夹，或按 README.md 安装开发依赖。
pause
