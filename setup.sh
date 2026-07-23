#!/bin/bash
# writeGOD 一键初始化脚本 (Linux/WSL2)
set -e

echo "================================"
echo "  writeGOD 环境初始化"
echo "================================"

# 检测 Python
echo ""
echo "[1/4] 检测 Python 环境..."
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "ERROR: 未找到 Python，请先安装 Python 3.11+"
    exit 1
fi
echo "  Python: $($PYTHON --version)"

# 创建虚拟环境（如果没有）
echo ""
echo "[2/4] 设置 Python 虚拟环境..."
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo "  虚拟环境已创建"
else
    echo "  虚拟环境已存在"
fi
source venv/bin/activate

# 安装 Python 依赖
echo ""
echo "[3/4] 安装 Python 依赖..."
pip install -r backend/requirements.txt --quiet
echo "  Python 依赖安装完成"

# 安装前端依赖
echo ""
echo "[4/4] 安装前端依赖..."
npm install --silent 2>/dev/null
cd frontend && npm install --silent 2>/dev/null && cd ..
echo "  前端依赖安装完成"

echo ""
echo "================================"
echo "  初始化完成！"
echo "  启动方式: npm run dev"
echo "  后端: http://localhost:5001"
echo "  前端: http://localhost:5173"
echo "================================"
