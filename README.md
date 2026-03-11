# DesignKit - Backend (FastAPI 服务)

这是 DesignKit 项目的后端服务，主要用于处理文件上传校验及与 `ODA File Converter` 的通信，将 CAD 文件转换成低版本。

## ⚙️ 环境依赖与预置说明

1. 需要 Python 3.10 或以上版本。
2. **安装系统底层要求**
**底层引擎要求**：请预先在您的系统内安装 [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)。这个底层 C++ 工具才是转换得以运行的基础前提。默认尝试会使用系统变量预设 `ODA_CONVERTER_PATH`（未提供默认寻找当前环境变量对应的执行体）。

## 🚀 本地开发启动说明

本项目使用 `uv` 作为依赖管理工具。请确保本地安装了 [uv](https://github.com/astral-sh/uv)。本地没有 Docker 环境也可正常运行，所有依赖均由 `uv` 统一管理。

### 1. 同步环境选项

使用 `uv` 自动创建环境并同步依赖。

```bash
uv sync
```

### 2. 运行本地开发服务器

使用 `uv` 来运行热重载服务器。

```bash
uv run uvicorn main:app --reload --port 8000
```

启动成功后，您可以在浏览器上访问本地文档来进行接口试验：

- API 交互文档 (Swagger UI): `http://127.0.0.1:8000/docs`
- 备用静态文档 (ReDoc): `http://127.0.0.1:8000/redoc`

## 📦 如何管理新依赖？

开发过程中，如果需要添加新依赖：

使用 `uv add` 来添加，添加后将自动更新 `pyproject.toml` 和 `uv.lock`。

```bash
uv add requests
```

> **注意：** 提交代码时，请带上更新后的 `pyproject.toml` 和 `uv.lock` 文件。

## 🐳 Docker 部署 (可选)

```bash
# 先删除旧的
docker stop designkit-container
docker rm designkit-container
docker rmi designkit:latest

# 再构建新的
docker build -t designkit:latest .
docker run -d -p 8000:8000 --name designkit-container designkit:latest
```
