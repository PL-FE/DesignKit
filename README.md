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

## 🐳 Docker 部署（推荐用于 DWG/DXF 转换）

> `DWG/DXF → 低版本 DWG` 转换依赖 `ODA File Converter`，容器启动时会自动拉起 `Xvfb`。  
> 为避免历史容器残留状态影响启动，**建议始终使用“删除旧容器后重建”的方式**，不要直接复用异常退出的旧容器。

### 1）删除旧容器（如存在）

```bash
docker rm -f designkit-container 2>/dev/null || true
```

### 2）构建镜像

```bash
docker build -t designkit:latest .
```

### 3）启动容器

```bash
docker run -d \
  --name designkit-container \
  -p 8000:8000 \
  --restart unless-stopped \
  designkit:latest
```

### 4）查看启动日志

```bash
docker logs -f designkit-container
```

正常情况下，日志中应看到类似输出：

- `🖥️ 启动虚拟 X11 显示服务器 Xvfb...`
- `✅ Xvfb 已启动`
- `🚀 启动 FastAPI 服务...`

### 5）验证服务是否正常

```bash
curl http://127.0.0.1:8000/
```

如果返回 HTTP 200，说明服务已成功启动。

### 常用维护命令

```bash
# 停止容器
docker stop designkit-container

# 删除容器
docker rm -f designkit-container

# 重新构建并启动（推荐）
docker rm -f designkit-container 2>/dev/null || true
docker build -t designkit:latest .
docker run -d --name designkit-container -p 8000:8000 --restart unless-stopped designkit:latest
```

### 常见问题

#### 1. 出现 `Server is already active for display 99`

这通常表示容器内 `Xvfb` 的历史锁状态未正确清理。  
当前版本的启动脚本已自动处理该问题；如果你仍然遇到它，请不要直接 `docker start` 旧容器，而是执行：

```bash
docker rm -f designkit-container 2>/dev/null || true
docker run -d --name designkit-container -p 8000:8000 --restart unless-stopped designkit:latest
```

#### 2. 容器启动了，但 DWG 转换失败

请优先检查容器日志：

```bash
docker logs designkit-container
```

重点确认以下内容：

- `ODA_CONVERTER_PATH` 是否存在且可执行
- `Xvfb` 是否成功启动
- `POST /api/convert` 调用时是否有 ODA 转换错误日志
