import json
import urllib.parse
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from services.board_layout import generate_psd_with_boxes
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/board/export")
async def board_export(
    files: list[UploadFile] = File(...),
    layout_data: str = Form(...),
    width: int = Form(1920),
    height: int = Form(1080),
    bg_color: str = Form("#FFFFFF"),
    dpi: int = Form(72)
):
    """
    图片展板导出（返回 PSD），接收前端给定的绝对坐标
    """
    if not files:
        raise HTTPException(status_code=400, detail="请上传至少一张图片")
        
    try:
        data = json.loads(layout_data)
        boxes = data.get("boxes", [])
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析 layout_data 失败: {str(e)}")

    if len(files) != len(boxes):
        logger.warning(f"上传文件数({len(files)})与坐标数({len(boxes)})不一致")

    file_bytes_list = []
    for f in files:
        file_bytes_list.append(await f.read())
        
    logger.info(f"[排版导出] 收到 {len(files)} 张图片, 尺寸={width}x{height}, 坐标数={len(boxes)}")

    try:
        psd_bytes = generate_psd_with_boxes(
            files=file_bytes_list, 
            boxes=boxes,
            width=width,
            height=height,
            bg_color=bg_color,
            dpi=dpi
        )
    except Exception as e:
        logger.error(f"[排版导出] 失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"导出 PSD 失败: {str(e)}")

    output_filename = "board_layout.psd"
    encoded_filename = urllib.parse.quote(output_filename)

    return Response(
        content=psd_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "X-Result-Size": f"{len(psd_bytes) / 1024:.1f}"
        }
    )
