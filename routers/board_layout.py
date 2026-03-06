import urllib.parse
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response, JSONResponse
from schemas import LayoutMode
from services.board_layout import generate_preview, generate_psd
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/board/preview")
async def board_preview(
    files: list[UploadFile] = File(...),
    layout: LayoutMode = Form(LayoutMode.MASONRY),
    width: int = Form(1920),
    height: int = Form(1080),
    gap: int = Form(10),
    bg_color: str = Form("#FFFFFF")
):
    """
    图片展板排版预览（返回 PNG）
    """
    if not files:
        raise HTTPException(status_code=400, detail="请上传至少一张图片")
        
    for f in files:
        ext = Path(f.filename or "file").suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            raise HTTPException(status_code=400, detail="不支持的图片格式")

    # 并发读取由于文件较小且在内存，也可同步读取
    file_bytes_list = []
    for f in files:
        file_bytes_list.append(await f.read())
        
    logger.info(f"[排版预览] 收到 {len(files)} 张图片, 模式={layout.value}, 尺寸={width}x{height}")

    try:
        png_bytes = generate_preview(
            files=file_bytes_list, 
            mode=layout.value,
            width=width,
            height=height,
            gap=gap,
            bg_color=bg_color
        )
    except Exception as e:
        logger.error(f"[排版预览] 失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成预览失败: {str(e)}")

    return Response(
        content=png_bytes,
        media_type="image/png"
    )

@router.post("/board/export")
async def board_export(
    files: list[UploadFile] = File(...),
    layout: LayoutMode = Form(LayoutMode.MASONRY),
    width: int = Form(1920),
    height: int = Form(1080),
    gap: int = Form(10),
    bg_color: str = Form("#FFFFFF"),
    dpi: int = Form(72)
):
    """
    图片展板导出（返回 PSD）
    """
    if not files:
        raise HTTPException(status_code=400, detail="请上传至少一张图片")
        
    file_bytes_list = []
    for f in files:
        file_bytes_list.append(await f.read())
        
    logger.info(f"[排版导出] 收到 {len(files)} 张图片, 模式={layout.value}, 尺寸={width}x{height}, DPI={dpi}")

    try:
        psd_bytes = generate_psd(
            files=file_bytes_list, 
            mode=layout.value,
            width=width,
            height=height,
            gap=gap,
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
