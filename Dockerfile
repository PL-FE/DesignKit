# ============================================================
# DesignKit CAD Converter API — Dockerfile
# 基础镜像：Ubuntu 22.04（满足 ODA GLIBC >= 2.28 要求）
# ============================================================

FROM ubuntu:22.04

# ---------- 构建参数 ----------
ARG DEBIAN_FRONTEND=noninteractive

# 本地 ODA .deb 包路径（相对于项目根目录）
ARG ODA_DEB_FILE=lib/ODAFileConverter_QT6_lnxX64_8.3dll_26.12.deb

# ---------- 系统依赖 ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python 运行时
    python3 \
    python3-pip \
    # gdebi 用于自动解决 .deb 包的依赖
    gdebi-core \
    # ODA File Converter 运行时依赖（Qt6 / OpenGL / 字体等）
    libgl1-mesa-glx \
    libglib2.0-0 \
    libfontconfig1 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxkbcommon0 \
    libegl1 \
    libxcb-util1 \
    # 工具
    curl \
    && rm -rf /var/lib/apt/lists/*

# ---------- 安装 ODA File Converter（本地 .deb）----------
COPY ${ODA_DEB_FILE} /tmp/oda_converter.deb

# 检测是否已安装，没有则用 gdebi 安装
# Ubuntu 22.04 额外需要 libxcb-util.so.0 软链接
RUN if command -v ODAFileConverter > /dev/null 2>&1; then \
        echo "✅ ODAFileConverter 已安装，跳过。"; \
    else \
        echo "🔧 正在安装 ODA File Converter ..." && \
        gdebi --non-interactive /tmp/oda_converter.deb && \
        echo "🔗 创建 libxcb-util.so.0 兼容软链接（Ubuntu 22.04 必需）..." && \
        ln -sf /usr/lib/x86_64-linux-gnu/libxcb-util.so.1 \
               /usr/lib/x86_64-linux-gnu/libxcb-util.so.0 && \
        echo "✅ ODA File Converter 安装完成。"; \
    fi \
    # 安装完成后删除 .deb 包，减小镜像体积
    && rm /tmp/oda_converter.deb

# ---------- 验证安装结果 ----------
RUN ODAFileConverter --version 2>/dev/null \
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
ENV ODA_CONVERTER_PATH=/usr/bin/ODAFileConverter
ENV HOST=0.0.0.0
ENV PORT=8000

# ---------- 暴露端口 ----------
EXPOSE 8000

# ---------- 健康检查 ----------
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# ---------- 启动命令 ----------
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
