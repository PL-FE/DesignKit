import urllib.parse
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
import tempfile
import os
import shutil
import logging
from services.ffmpeg_service import make_gif
from schemas import GifFormat

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/video/gif")
async def generate_gif_endpoint(
    file: UploadFile = File(...),
    start_time: str = Form("0"),
    duration: str = Form("5"),
    fps: int = Form(15),
    output_fmt: GifFormat = Form(GifFormat.GIF)
):
    """
    动图制造与截帧
    """
    filename = file.filename or "unnamed_video"
    input_dir = tempfile.mkdtemp(prefix="video_gif_in_")
    
    try:
        input_path = os.path.join(input_dir, filename)
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            
        logger.info(f"[视频转动图/封面] 文件: {filename}, 从 {start_time} 开始截取 {duration}秒, fmt: {output_fmt.value}")
        
        # 调用服务
        result_path = await make_gif(input_path, start_time, duration, fps, output_fmt.value)
        
        base_name = Path(filename).stem
        ext = "jpg" if output_fmt.value == "jpg" else output_fmt.value
        output_filename = f"{base_name}_cover.{ext}"
        encoded_filename = urllib.parse.quote(output_filename)
        
        def cleanup():
            shutil.rmtree(input_dir, ignore_errors=True)
            if os.path.exists(result_path):
                os.remove(result_path)
                
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
        logger.error(f"处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        logger.error(f"系统错误: {e}")
        raise HTTPException(status_code=500, detail="截取时发生系统级错误")
