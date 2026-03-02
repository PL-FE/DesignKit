#!/bin/bash
set -e

echo "🖥️  启动虚拟 X11 显示服务器 Xvfb..."
Xvfb :99 -screen 0 1024x768x24 -nolisten tcp &
XVFB_PID=$!
sleep 1

if ! kill -0 "$XVFB_PID" 2>/dev/null; then
    echo "❌ Xvfb 启动失败，退出。"
    exit 1
fi
echo "✅ Xvfb 已启动（PID=$XVFB_PID, DISPLAY=:99）"

echo "🚀 启动 FastAPI 服务..."
exec python3 -m uvicorn main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --workers 2
