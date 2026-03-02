# ============================================================
# DesignKit CAD Converter API — Dockerfile
# 基础镜像：Ubuntu 22.04（满足 ODA GLIBC >= 2.28 要求）
# 使用 AppImage 版本：自包含 Qt 运行时，无需任何图形环境依赖
# ============================================================

FROM ubuntu:22.04

# ---------- 构建参数 ----------
ARG DEBIAN_FRONTEND=noninteractive

# 本地 ODA AppImage 路径（相对于项目根目录）
ARG ODA_APPIMAGE=lib/ODAFileConverter_QT6_lnxX64_8.3dll_27.1.AppImage

# ---------- 系统依赖（最小化）----------
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python 运行时
    python3 \
    python3-pip \
    # ODAFileConverter 底层运行时依赖（AppImage 自包含 Qt，但不含这些系统级库）
    libgl1-mesa-glx \
    libglib2.0-0 \
    libfontconfig1 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxkbcommon0 \
    libegl1 \
    libxcb-util1 \
    # Xvfb：AppImage 内置 Qt 仅含 xcb 插件（无 offscreen），需虚拟 X11 显示
    xvfb \
    # 健康检查工具
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---------- 安装 ODA File Converter（AppImage 解压方式，无需 FUSE）----------
COPY ${ODA_APPIMAGE} /tmp/ODAFileConverter.AppImage

RUN chmod +x /tmp/ODAFileConverter.AppImage \
    # --appimage-extract：解压到 squashfs-root，完全绕过 FUSE 权限要求
    && /tmp/ODAFileConverter.AppImage --appimage-extract \
    && mv squashfs-root /opt/ODAFileConverter \
    && rm /tmp/ODAFileConverter.AppImage \
    # 打印目录结构，帮助确认可执行文件实际路径
    && echo "📂 AppImage 内部结构：" \
    && find /opt/ODAFileConverter -maxdepth 3 \( -name "ODA*" -o -name "AppRun" \) -type f \
    && echo "✅ ODA File Converter AppImage 解压完成"

# ---------- 验证安装结果 ----------
RUN /opt/ODAFileConverter/ODAFileConverter --version 2>/dev/null \
    && echo "✅ ODAFileConverter 验证通过。" \
    || echo "⚠️  ODAFileConverter 验证失败，请检查安装日志。"

# ---------- 设置工作目录 ----------
WORKDIR /app

# ---------- 安装 Python 依赖（利用 Docker 层缓存）----------
COPY requirements.txt .
RUN pip3 install --no-cache-dir \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    -r requirements.txt

# ---------- 复制应用代码 ----------
COPY main.py .
COPY schemas.py .
COPY routers/ ./routers/
COPY services/ ./services/

# ---------- 环境变量 ----------
ENV ODA_CONVERTER_PATH=/opt/ODAFileConverter/usr/bin/ODAFileConverter
# AppImage 解压后库文件在 usr/bin/，Qt 插件在 usr/plugins/
ENV LD_LIBRARY_PATH=/opt/ODAFileConverter/usr/bin
ENV QT_PLUGIN_PATH=/opt/ODAFileConverter/usr/plugins
# AppImage 内置 Qt 只有 xcb 插件（无 offscreen），用 Xvfb 提供虚拟 X11
ENV QT_QPA_PLATFORM=xcb
ENV DISPLAY=:99
ENV HOST=0.0.0.0
ENV PORT=8000

# ---------- 暴露端口 ----------
EXPOSE 8000

# ---------- 健康检查 ----------
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# ---------- 启动命令 ----------
# xvfb-run 自动启动虚拟 X11，ODA AppImage 的 xcb 插件可正常初始化
CMD ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1024x768x24",\
     "python3", "-m", "uvicorn", "main:app",\
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
