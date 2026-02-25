import os
import tempfile
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from schemas import TargetVersion
from services.oda_converter import convert_dwg_version
import urllib.parse
from starlette.background import BackgroundTask

router = APIRouter()

def remove_file(path: str):
    """用于后台任务删除临时文件"""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"Failed to delete temp file {path}: {e}")

@router.post("/convert")
async def convert_file(
    file: UploadFile = File(...),
    target_version: TargetVersion = Form(...)
):
    # 1. 校验文件后缀
    filename = file.filename or "unnamed.dwg"
    ext = Path(filename).suffix.lower()
    if ext not in [".dwg", ".dxf"]:
        raise HTTPException(status_code=400, detail="不支持的文件格式，仅支持 .dwg 和 .dxf")
        
    print(f"接收到文件: {filename}, 大小: {file.size} 字节, 目标版本: {target_version.value}")
    
    # 2. 保存上传文件到临时输入目录
    input_dir = tempfile.mkdtemp(prefix="oda_in_")
    input_file_path = os.path.join(input_dir, filename)
    
    try:
        with open(input_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 3. 调用 ODA 转换服务
        try:
            converted_file_path = await convert_dwg_version(
                input_file_path=input_file_path,
                target_version=target_version.value
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"转换失败: {str(e)}")
            
        # 4. 构建返回的文件名
        base_name = os.path.splitext(filename)[0]
        output_filename = f"{base_name}_{target_version.value}.dwg"
        encoded_filename = urllib.parse.quote(output_filename)
        
        # 5. 返回文件流 (响应结束后清理转换后的文件以及输入目录)
        def cleanup():
            remove_file(converted_file_path)
            shutil.rmtree(input_dir, ignore_errors=True)
            
        return FileResponse(
            path=converted_file_path,
            filename=output_filename,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            },
            background=BackgroundTask(cleanup)
        )
        
    except HTTPException:
        # 如果抛出HTTPException，也需清理输入目录
        shutil.rmtree(input_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))
