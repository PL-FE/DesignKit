# DesignKit 开发文档

## 架构设计

```
前端（交互层）：可视化操作 → 上传 CAD 文件 + 选择目标版本 → 发送请求
    ↓（HTTP POST，multipart/form-data）
后端（处理层）：接收文件 → 校验合法性 → 调用 ODA File Converter → 返回文件流
    ↓
前端：接收文件流 → 触发浏览器下载 → 完成转换
```

---

## 前端技术栈

| 类别       | 技术                    | 说明                                    |
| ---------- | ----------------------- | --------------------------------------- |
| 核心框架   | Vue3 + Vite             | SFC + TypeScript                        |
| UI 库      | Element Plus            | 上传/表单/提示等核心组件                |
| 原子化 CSS | UnoCSS                  | presetUno + presetAttributify           |
| 状态管理   | Pinia                   | 保存用户版本偏好（持久化 localStorage） |
| 工具库     | VueUse                  | 文件上传/下载、防抖、本地存储           |
| 图标库     | Iconify                 | 按需加载图标                            |
| 效率插件   | unplugin-auto-import    | 自动导入 Vue/VueUse/Pinia API           |
| 效率插件   | unplugin-vue-components | 自动导入 Element Plus 组件              |

---

## 后端技术栈

| 类别     | 技术               | 说明                                       |
| -------- | ------------------ | ------------------------------------------ |
| 核心框架 | FastAPI (Python)   | 异步高性能 Web 框架                        |
| CAD 处理 | ODA File Converter | 免费命令行工具，通过 subprocess 调用       |
| 异步处理 | asyncio            | 异步执行文件转换任务                       |
| 数据校验 | Pydantic           | 校验上传文件格式和请求参数                 |
| 接口文档 | Swagger UI + ReDoc | FastAPI 自动生成，访问 `/docs` 或 `/redoc` |

---

## API 接口文档

### POST `/api/convert`

CAD 文件版本转换接口。

**请求格式**：`multipart/form-data`

| 参数           | 类型   | 必填 | 说明                         |
| -------------- | ------ | ---- | ---------------------------- |
| file           | File   | ✅   | CAD 文件（支持 .dwg / .dxf） |
| target_version | string | ✅   | 目标版本（见下方版本列表）   |

**支持的目标版本**：

| 版本标识 | 对应 AutoCAD 版本 |
| -------- | ----------------- |
| ACAD9    | AutoCAD R9        |
| ACAD10   | AutoCAD R10       |
| ACAD12   | AutoCAD R12       |
| ACAD14   | AutoCAD R14       |
| ACAD2000 | AutoCAD 2000      |
| ACAD2004 | AutoCAD 2004      |
| ACAD2007 | AutoCAD 2007      |
| ACAD2010 | AutoCAD 2010      |
| ACAD2013 | AutoCAD 2013      |
| ACAD2018 | AutoCAD 2018      |

**成功响应**：

- `Content-Type`: `application/octet-stream`
- `Content-Disposition`: `attachment; filename="<原文件名>_<目标版本>.<扩展名>"`
- Body: 转换后的文件二进制流

**错误响应**：

```json
{
  "detail": "错误描述信息"
}
```

| HTTP 状态码 | 说明                          |
| ----------- | ----------------------------- |
| 400         | 文件格式不支持 / 目标版本无效 |
| 500         | 转换失败（ODA 处理异常）      |

---

## 部署架构

```
                    Nginx
                   ┌─────────────────────┐
用户浏览器 ──→     │  /       → 前端静态文件  │
                   │  /api/   → FastAPI     │
                   └─────────────────────┘
                          ↓
                   Docker 容器（FastAPI）
                          ↓
                   ODA File Converter
```

- **前端**：Nginx 静态文件服务
- **后端**：Docker 容器部署 FastAPI 应用
- **反向代理**：Nginx 将 `/api/` 请求转发给 FastAPI 容器

---

## 目录结构

```
DesignKit/
├── web/                    # 前端项目
│   ├── src/
│   │   ├── api/            # API 调用封装
│   │   ├── stores/         # Pinia 状态管理
│   │   ├── views/          # 页面组件
│   │   └── App.vue         # 根组件
│   ├── uno.config.ts       # UnoCSS 配置
│   └── vite.config.ts      # Vite 配置
├── server/                 # 后端项目
│   ├── routers/            # API 路由
│   ├── services/           # 业务逻辑（ODA 封装）
│   ├── schemas.py          # Pydantic 数据模型
│   ├── main.py             # FastAPI 入口
│   └── requirements.txt    # Python 依赖
├── nginx.conf              # Nginx 配置
├── Dockerfile              # 后端 Docker 镜像
└── docker-compose.yml      # 容器编排
```
