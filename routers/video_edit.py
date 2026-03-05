import urllib.parse
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
import tempfile
import os
import shutil
import logging
from services.ffmpeg_service import edit_video

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/video/edit")
async def edit_video_endpoint(
    file: UploadFile = File(...),
    trim_start: str = Form("0"),
    trim_end: str = Form(""),
    crop: str = Form(""),
    remove_audio: bool = Form(False),
    speed: float = Form(1.0)
):
    """
    轻量视频剪辑器
    """
    filename = file.filename or "unnamed_video"
    input_dir = tempfile.mkdtemp(prefix="video_edit_in_")
    
    try:
        input_path = os.path.join(input_dir, filename)
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            
        params = {
            "trim_start": trim_start,
            "trim_end": trim_end,
            "crop": crop,
            "remove_audio": remove_audio,
            "speed": speed,
        }
        logger.info(f"[轻量视频剪辑] 接收文件: {filename}, 参数: {params}")
        
        # 调用核心剪辑服务
        result_path = await edit_video(input_path, params)
        
        # 编码输出文件名
        base_name = Path(filename).stem
        output_filename = f"{base_name}_edited.mp4"
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
        logger.error(f"剪辑失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        logger.error(f"剪辑系统级错误: {e}")
        raise HTTPException(status_code=500, detail="执行剪辑时发生异常")
