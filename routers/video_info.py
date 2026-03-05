import urllib.parse
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
import tempfile
import os
import shutil
import logging
from services.ffmpeg_service import execute_ffprobe

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/video/info")
async def get_video_info_endpoint(
    file: UploadFile = File(...),
):
    """
    获取媒体的深度信息（透视仪）
    - 返回视频的 format 与 streams 原始 JSON
    """
    filename = file.filename or "unnamed"
    input_dir = tempfile.mkdtemp(prefix="video_info_in_")
    
    try:
        input_path = os.path.join(input_dir, filename)
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            
        logger.info(f"[视频信息透视] 接收到文件: {filename}")
        
        # 调用核心服务
        result_json = await execute_ffprobe(input_path)
        return result_json
        
    except RuntimeError as e:
        logger.error(f"处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"未知错误: {e}")
        raise HTTPException(status_code=500, detail="解析媒体信息时发生系统错误")
    finally:
        # 信息提取完成后，直接清理暂存的文件
        shutil.rmtree(input_dir, ignore_errors=True)
