#!/usr/bin/env bash
# LanCloud 一键启动（Linux / macOS）
# 用法：./start.sh  或  bash start.sh
set -e
cd "$(dirname "$0")"

PY="python3"
command -v "$PY" >/dev/null 2>&1 || PY="python"

echo "[1/3] 检查/创建虚拟环境 .venv ..."
if [ ! -d ".venv" ]; then
  "$PY" -m venv .venv
fi

echo "[2/3] 安装依赖 ..."
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "[3/3] 启动 LanCloud ..."
exec .venv/bin/python run.py "$@"
