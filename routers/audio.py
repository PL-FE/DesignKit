import urllib.parse
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
import tempfile
import os
import shutil
import logging
import json
from typing import List # Added for List[UploadFile]
import zipfile # Added for zip file creation
from services.ffmpeg_service import merge_audio

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/audio/merge")
async def merge_audio_endpoint(
    files: list[UploadFile] = File(...),
    order: str = Form(...), # 接收一个 JSON 字符串，例如 "[0, 2, 1]"
):
    """
    音乐合并：支持多文件上传及顺序调整
    """
    try:
        order_list = json.loads(order)
    except Exception:
        raise HTTPException(status_code=400, detail="无效的顺序参数")
        
    if len(files) != len(order_list):
        raise HTTPException(status_code=400, detail="文件数量与顺序不匹配")

    input_dir = tempfile.mkdtemp(prefix="audio_merge_in_")
    saved_paths = []
    
    try:
        # 1. 保存所有文件
        for i, file in enumerate(files):
            file_path = os.path.join(input_dir, f"file_{i}_{file.filename}")
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            saved_paths.append(file_path)
            
        # 2. 按照 order 重新排序路径
        ordered_paths = [saved_paths[idx] for idx in order_list]
        
        logger.info(f"[音频合并] 接收到 {len(files)} 个文件，顺序: {order_list}")
        
        # 3. 调用核心服务
        result_path = await merge_audio(ordered_paths)
        
        output_filename = "merged_audio.mp3"
        encoded_filename = urllib.parse.quote(output_filename)
        
        def cleanup():
            shutil.rmtree(input_dir, ignore_errors=True)
            if os.path.exists(result_path):
                os.remove(result_path)
                
        return FileResponse(
            path=result_path,
            filename=output_filename,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            },
            background=BackgroundTask(cleanup)
        )
        
    except Exception as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        logger.error(f"音频合并错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))
