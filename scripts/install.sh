#!/usr/bin/env bash
# LanCloud 一键安装脚本（Linux / macOS）
# 用法：bash scripts/install.sh
set -e
cd "$(dirname "$0")/.."

echo "== LanCloud 安装脚本 =="
echo "[1/4] 检查 Python ..."
PY="python3"
command -v "$PY" >/dev/null 2>&1 || PY="python"
"$PY" --version

echo "[2/4] 创建虚拟环境 ..."
"$PY" -m venv .venv

echo "[3/4] 安装依赖 ..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "[4/4] 启动测试 ..."
echo "安装完成！启动命令："
echo "    ./start.sh"
echo "首次启动后浏览器访问 http://127.0.0.1:8080"
echo "默认管理员：admin / admin123（请登录后尽快修改 data/config.json 中的密码）"
