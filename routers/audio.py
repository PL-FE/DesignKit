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
from services.ffmpeg_service import separate_vocals, merge_audio

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/audio/vocal-removal") # Changed endpoint path
async def vocal_removal_endpoint(files: List[UploadFile] = File(...)): # Changed parameter to List[UploadFile]
    """
    接收一个或多个音频文件，提取伴奏。
    如果是多个文件，则返回 ZIP 压缩包；单个文件则直接返回伴奏文件。
    """
    if not files:
        raise HTTPException(status_code=400, detail="未上传文件")

    input_dir = tempfile.mkdtemp(prefix="vocal_removal_input_") # Changed prefix
    output_files = [] # 存储生成的伴奏路径和原始文件名对
    
    try:
        # 串行处理每个文件，避免资源耗尽
        for i, file in enumerate(files):
            filename = file.filename or f"audio_{i}.mp3"
            input_path = os.path.join(input_dir, f"input_{i}_{filename}")
            
            with open(input_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            logger.info(f"[音频人声去除] 正在处理第 {i+1}/{len(files)} 个文件: {filename}")
            
            try:
                # 调用核心服务
                result_path = await separate_vocals(input_path)
                
                # 记录结果
                if result_path and os.path.exists(result_path):
                    base_name = Path(filename).stem
                    ext = Path(result_path).suffix
                    output_name = f"{base_name}_accompaniment{ext}"
                    output_files.append((result_path, output_name))
                    logger.info(f"[音频人声去除] 成功生成结果: {output_name}")
                else:
                    logger.error(f"[音频人声去除] 文件 {filename} 处理成功但未找到输出路径")
            except Exception as e:
                logger.error(f"[音频人声去除] 文件 {filename} 处理失败: {str(e)}")
                # 继续处理后续文件，不一定要全部中断

        # 根据结果数量决定返回方式
        if len(output_files) == 1:
            result_path, output_filename = output_files[0]
            encoded_filename = urllib.parse.quote(output_filename)
            ext = Path(result_path).suffix
            media_type = "audio/mpeg" if ext == ".mp3" else "audio/wav"
            
            def cleanup():
                shutil.rmtree(input_dir, ignore_errors=True)
                if os.path.exists(result_path):
                    os.remove(result_path)
                    
            return FileResponse(
                path=result_path,
                filename=output_filename,
                media_type=media_type,
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
                },
                background=BackgroundTask(cleanup)
            )
        else:
            # 多个文件，打包成 ZIP
            zip_path = tempfile.mktemp(suffix=".zip")
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for path, name in output_files:
                    zipf.write(path, name)
            
            def cleanup_all():
                shutil.rmtree(input_dir, ignore_errors=True)
                for path, _ in output_files:
                    if os.path.exists(path):
                        os.remove(path)
                if os.path.exists(zip_path):
                    os.remove(zip_path)

            encoded_zip_name = urllib.parse.quote("accompaniments.zip")
            return FileResponse(
                path=zip_path,
                filename="accompaniments.zip",
                media_type="application/zip",
                headers={
                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_zip_name}",
                },
                background=BackgroundTask(cleanup_all)
            )

    except Exception as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        # 清理已生成的文件
        for path, _ in output_files:
            if os.path.exists(path):
                os.remove(path)
        logger.error(f"人声分离失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"人声去除处理错误: {str(e)}")

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
