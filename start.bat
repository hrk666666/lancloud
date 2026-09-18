@echo off
chcp 65001 >nul
rem LanCloud 一键启动（Windows）
rem 用法：双击 start.bat 即可
cd /d "%~dp0"

echo [1/3] 检查 Python ...
where python >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python，请先安装 Python 3.9+ 并勾选 "Add to PATH"
  pause
  exit /b 1
)

echo [2/3] 安装依赖 ...
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

echo [3/3] 启动 LanCloud ...
python run.py
pause
