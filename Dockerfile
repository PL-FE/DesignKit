FROM python:3.11-slim

# 安装必要系统依赖（ODA Converter 运行可能需要的系统库）
RUN apt-get update && apt-get install -y \
    wget \
    dpkg \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# 假设 ODA File Converter 使用的是 Debian 包，在真实生产中你需要将正确的安装包放入上下文或者在线下载。
# 此处我们配置 ODA_CONVERTER_PATH 为假定路径。
# 示例: RUN wget <oda_url>.deb && dpkg -i <oda_deb_file>
ENV ODA_CONVERTER_PATH="/usr/bin/ODAFileConverter"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 暴露端口
EXPOSE 8000

# 启动服务
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
