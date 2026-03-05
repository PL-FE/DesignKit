import urllib.parse
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
import tempfile
import os
import shutil
import logging
from services.ffmpeg_service import convert_format
from schemas import VideoFormat

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/video/convert")
async def convert_video_endpoint(
    file: UploadFile = File(...),
    target_format: VideoFormat = Form(VideoFormat.MP4),
):
    """
    全能格式转换中心
    - 支持视频转视频（MP4, MOV 等）
    - 支持提取音频（MP3, AAC 等）
    """
    filename = file.filename or "unnamed_video"
    input_dir = tempfile.mkdtemp(prefix="video_convert_in_")
    
    try:
        input_path = os.path.join(input_dir, filename)
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            
        logger.info(f"[视频格式转换] 接收到文件: {filename}, 目标格式: {target_format.value}")
        
        # 调用核心服务
        result_path = await convert_format(input_path, target_format.value)
        
        # 编码输出文件名
        base_name = Path(filename).stem
        output_filename = f"{base_name}_converted.{target_format.value}"
        encoded_filename = urllib.parse.quote(output_filename)
        
        def cleanup():
            shutil.rmtree(input_dir, ignore_errors=True)
            if os.path.exists(result_path):
                os.remove(result_path)
                
        # 通过 FileResponse 返回并在完毕后清除所有内容
        return FileResponse(
            path=result_path,
            filename=output_filename,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            },
            background=BackgroundTask(cleanup)
        )
        
    except RuntimeError as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        logger.error(f"转换处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        logger.error(f"转换系统错误: {e}")
        raise HTTPException(status_code=500, detail="媒体转换时发生系统错误")
