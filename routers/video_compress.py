import urllib.parse
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
import tempfile
import os
import shutil
import logging
from services.ffmpeg_service import compress_video
from schemas import CompressLevel

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/video/compress")
async def compress_video_endpoint(
    file: UploadFile = File(...),
    level: CompressLevel = Form(CompressLevel.MEDIUM),
):
    """
    智能体积压缩器
    """
    filename = file.filename or "unnamed_video"
    input_dir = tempfile.mkdtemp(prefix="video_compress_in_")
    
    try:
        input_path = os.path.join(input_dir, filename)
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            
        logger.info(f"[视频压缩] 接收到文件: {filename}, 压缩等级: {level.value}")
        
        # 调用核心服务进行压缩
        result_path = await compress_video(input_path, level.value)
        
        # 编码输出文件名
        base_name = Path(filename).stem
        output_filename = f"{base_name}_compressed.mp4"
        encoded_filename = urllib.parse.quote(output_filename)
        
        def cleanup():
            shutil.rmtree(input_dir, ignore_errors=True)
            if os.path.exists(result_path):
                os.remove(result_path)
                
        # 返回流
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
        logger.error(f"压缩处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        logger.error(f"系统错误: {e}")
        raise HTTPException(status_code=500, detail="媒体压缩时发生系统错误")
