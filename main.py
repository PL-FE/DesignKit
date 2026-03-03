from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import converter, image

app = FastAPI(
    title="DesignKit API",
    description="面向设计与工程的在线工具集 API，提供 CAD 转换、图片压缩等功能",
    version="2.0.0"
)

# 配置 CORS，开发环境允许所有来源，生产环境按需配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(converter.router, prefix="/api")
app.include_router(image.router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to DesignKit API - 设计工程工具集"}
