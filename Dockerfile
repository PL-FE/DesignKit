# ============================================================
# DesignKit CAD Converter API — Dockerfile
# 基础镜像：Ubuntu 22.04 (ODA File Converter 官方支持)
# ============================================================

FROM ubuntu:22.04

# ---------- 基本构建参数 ----------
ARG DEBIAN_FRONTEND=noninteractive
ARG ODA_DEB_URL=""
# ODA File Converter .deb 包的下载地址，构建时通过 --build-arg 传入
# 例如: docker build --build-arg ODA_DEB_URL=https://example.com/oda.deb .
# 如果已将 .deb 文件放到项目根目录，也可以改用 COPY 方式（见下方注释）

# ---------- 系统依赖 ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python 运行时
    python3.11 \
    python3.11-venv \
    python3-pip \
    # ODA File Converter 运行时依赖（Qt / OpenGL / 字体等）
    libgl1-mesa-glx \
    libglib2.0-0 \
    libfontconfig1 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxkbcommon0 \
    libegl1 \
    # 下载工具
    curl \
    wget \
    # 清理缓存
    && rm -rf /var/lib/apt/lists/*

# ---------- 安装 ODA File Converter ----------
# 方式一（推荐）：通过构建参数下载官方 .deb 包安装
# 请将 ODA_DEB_URL 替换为真实的下载地址（需要 ODA 授权）
RUN if [ -n "$ODA_DEB_URL" ]; then \
        wget -q "$ODA_DEB_URL" -O /tmp/oda_converter.deb && \
        dpkg -i /tmp/oda_converter.deb || apt-get install -f -y && \
        rm /tmp/oda_converter.deb; \
    else \
        echo "⚠️  未提供 ODA_DEB_URL，跳过 ODA File Converter 安装。"; \
        echo "   请在运行时通过 ODA_CONVERTER_PATH 环境变量指定可执行文件路径。"; \
    fi

# 方式二（离线构建）：将 .deb 包放到项目根目录后取消下方注释并注释方式一
# COPY ODAFileConverter_QT6_lnxX64_8.3.2.deb /tmp/oda_converter.deb
# RUN dpkg -i /tmp/oda_converter.deb || apt-get install -f -y \
#     && rm /tmp/oda_converter.deb

# ---------- 设置工作目录 ----------
WORKDIR /app

# ---------- 安装 Python 依赖（利用 Docker 层缓存）----------
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# ---------- 复制应用代码 ----------
COPY main.py .
COPY schemas.py .
COPY routers/ ./routers/
COPY services/ ./services/

# ---------- 环境变量 ----------
# ODA File Converter 默认安装路径（Ubuntu .deb 通常为此路径）
ENV ODA_CONVERTER_PATH=/usr/bin/ODAFileConverter
# uvicorn 监听地址与端口
ENV HOST=0.0.0.0
ENV PORT=8000

# ---------- 暴露端口 ----------
EXPOSE 8000

# ---------- 健康检查 ----------
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# ---------- 启动命令 ----------
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
