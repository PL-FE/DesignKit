import ssl
import os

# 全局跳过 SSL 证书验证，解决某些环境下无法下载模型的问题
ssl._create_default_https_context = ssl._create_unverified_context

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import converter, image, video_info, video_convert, video_compress, video_gif, video_edit, board_layout, audio

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
app.include_router(video_info.router, prefix="/api")
app.include_router(video_convert.router, prefix="/api")
app.include_router(video_compress.router, prefix="/api")
app.include_router(video_gif.router, prefix="/api")
app.include_router(video_edit.router, prefix="/api")
app.include_router(board_layout.router, prefix="/api")
app.include_router(audio.router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to DesignKit API - 设计工程工具集"}
