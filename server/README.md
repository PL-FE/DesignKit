# DesignKit - Backend (FastAPI 服务)

这是 DesignKit 项目的后端服务，主要用于处理文件上传校验及与 `ODA File Converter` 的通信，将 CAD 文件转换成低版本。

## ⚙️ 环境依赖与预置说明

1. 需要 Python 3.10 或以上版本。
2. **底层引擎要求**：请预先在您的服务器系统内安装 [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)。这个底层 C++ 工具才是转换得以运行的基础前提。默认尝试会使用系统变量预设 `ODA_CONVERTER_PATH`（未提供默认寻找当前环境变量对应的执行体）。

## 🚀 本地开发启动说明

进入在 `server` 根目录环境下执行：

### 1. 创建并激活虚拟环境 (可选但是强烈推荐)

```bash
# 创建名为 venv 的虚拟环境
python3 -m venv venv

# 激活环境 (Linux/MacOS)
source venv/bin/activate
# 激活环境 (Windows)
# venv\Scripts\activate
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 运行本地开发服务器

使用 `uvicorn` 热重载快速启动服务。

```bash
uvicorn main:app --reload --port 8000
```

启动成功后，您可以在浏览器上访问本地文档来进行接口试验：

- API 交互文档 (Swagger UI): `http://127.0.0.1:8000/docs`
- 备用静态文档 (ReDoc): `http://127.0.0.1:8000/redoc`

## 📦 如何管理补充/冻结新的依赖？

开发过程中，如果需要添加了新依赖（如执行了 `pip install requests`）：

请一定要随时更新依赖清单 `requirements.txt`：

```bash
pip freeze > requirements.txt
```

> **注意：** FastAPI 由于生态较为松散集成度高，如果使用了其他附加插件（诸如 SQLAlchemy, SQLModel, Alembic），记得一并将其使用 `pip freeze` 进行固定，以防远端构建挂掉。

## 🐳 Docker 环境独立测试

如果你不想通过 python 环境在本地运行跑起来，且服务器环境含有能正常跑的 `docker-compose` 和对应配置了 ODA 环境容器：

```bash
docker build -t designkit-backend .
docker run -p 8000:8000 designkit-backend
```

一般情况，直接回退一级目录使用项目根目录下的 `docker-compose up -d --build` 是最直观简单的组合运行手段。
