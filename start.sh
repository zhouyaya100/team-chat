#!/bin/bash

echo "================================"
echo "  Team Chat - 启动脚本"
echo "================================"
echo ""

cd "$(dirname "$0")"

echo "[1/3] 检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误：未找到 Python3，请先安装 Python 3.8+"
    exit 1
fi
echo "✅ Python 环境正常"

echo ""
echo "[2/3] 安装依赖..."
pip3 install -r requirements.txt -q
echo "✅ 依赖安装完成"

echo ""
echo "[3/3] 启动服务..."
echo ""
python3 app.py
