#!/usr/bin/env bash
set -e

echo "========================================================"
echo "  FreeSub WebUI - 本地智能测活与节点订阅中心"
echo "  端口: 18168"
echo "========================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 自动处理 Debian/Ubuntu PEP 668 (externally-managed-environment)
if [ ! -d ".venv" ]; then
    echo "[*] 正在创建独立虚拟环境 (.venv)..."
    python3 -m venv .venv 2>/dev/null || python -m venv .venv 2>/dev/null || true
fi

if [ -f ".venv/bin/activate" ]; then
    echo "[*] 激活 Python 虚拟环境 (.venv)..."
    source .venv/bin/activate
    pip install -q -r requirements-web.txt
    echo "[*] 启动服务: http://127.0.0.1:18168"
    python -m web.main
else
    echo "[*] 未安装 python3-venv 组件，使用 --break-system-packages 安装依赖..."
    pip install -q --break-system-packages -r requirements-web.txt 2>/dev/null || pip install -q -r requirements-web.txt
    echo "[*] 启动服务: http://127.0.0.1:18168"
    python3 -m web.main || python -m web.main
fi
