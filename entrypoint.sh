#!/bin/bash
set -euo pipefail

DISPLAY_VALUE="${DISPLAY:-:99}"
DISPLAY_NUM="${DISPLAY_VALUE#:}"
LOCK_FILE="/tmp/.X${DISPLAY_NUM}-lock"
SOCKET_FILE="/tmp/.X11-unix/X${DISPLAY_NUM}"
XVFB_PID=""
XVFB_STARTED=0
APP_PID=""

cleanup() {
    local exit_code=$?

    if [[ "${XVFB_STARTED}" == "1" && -n "${XVFB_PID}" ]] && kill -0 "${XVFB_PID}" 2>/dev/null; then
        echo "🛑 正在关闭 Xvfb（PID=${XVFB_PID}）..."
        kill "${XVFB_PID}" 2>/dev/null || true
        wait "${XVFB_PID}" 2>/dev/null || true
        rm -f "${LOCK_FILE}" "${SOCKET_FILE}"
    fi

    exit "${exit_code}"
}

trap cleanup EXIT INT TERM

if [[ -f "${LOCK_FILE}" ]]; then
    EXISTING_PID="$(tr -dc '0-9' < "${LOCK_FILE}" 2>/dev/null || true)"
    if [[ -n "${EXISTING_PID}" ]] && kill -0 "${EXISTING_PID}" 2>/dev/null; then
        echo "ℹ️  检测到 DISPLAY=${DISPLAY_VALUE} 已有 Xvfb 在运行（PID=${EXISTING_PID}），直接复用。"
    else
        echo "⚠️  检测到失效的 Xvfb 锁文件，正在清理..."
        rm -f "${LOCK_FILE}" "${SOCKET_FILE}"
    fi
fi

if [[ ! -f "${LOCK_FILE}" ]]; then
    echo "🖥️  启动虚拟 X11 显示服务器 Xvfb..."
    mkdir -p /tmp/.X11-unix
    Xvfb "${DISPLAY_VALUE}" -screen 0 1024x768x24 -nolisten tcp &
    XVFB_PID=$!
    XVFB_STARTED=1
    sleep 1

    if ! kill -0 "${XVFB_PID}" 2>/dev/null; then
        echo "❌ Xvfb 启动失败，退出。"
        exit 1
    fi

    echo "✅ Xvfb 已启动（PID=${XVFB_PID}, DISPLAY=${DISPLAY_VALUE}）"
fi

echo "🚀 启动 FastAPI 服务..."
python3 -m uvicorn main:app \
    --host "${HOST:-0.0.0.0}" \
    --port "${PORT:-8000}" \
    --workers 2 &
APP_PID=$!

wait "${APP_PID}"
