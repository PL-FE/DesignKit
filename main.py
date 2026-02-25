from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import converter

app = FastAPI(
    title="DesignKit CAD Converter API",
    description="在线 CAD 版本转换工具 API",
    version="1.0.0"
)

# 配置 CORS，开发环境允许所有来源，生产环境按需配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册转换路由
app.include_router(converter.router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to DesignKit CAD Converter API"}
