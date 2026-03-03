import os
import io
import tempfile
import urllib.parse
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from services.image_compressor import compress_to_target_size, SUPPORTED_INPUT_FORMATS

router = APIRouter()


@router.post("/image/compress")
async def compress_image(
    file: UploadFile = File(...),
    target_kb: float | None = Form(None, description="目标文件大小（KB），不填则仅做尺寸缩放或格式转换"),
    max_width: int | None = Form(None, description="最大宽度（像素）"),
    max_height: int | None = Form(None, description="最大高度（像素）"),
    output_format: str = Form("jpeg", description="输出格式：jpeg / png / webp"),
    strip_exif: bool = Form(True, description="是否清除 EXIF 元数据"),
):
    """
    图片压缩接口
    - 支持指定目标大小（KB），使用二分法自动调整质量
    - 支持限制最大宽高（等比缩放）
    - 支持输出格式转换（JPEG / PNG / WebP）
    - 支持清除 EXIF 元数据
    """
    filename = file.filename or "image.jpg"
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_INPUT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式 '{ext}'，支持：{', '.join(SUPPORTED_INPUT_FORMATS)}"
        )

    if output_format.lower() not in ("jpeg", "png", "webp"):
        raise HTTPException(status_code=400, detail="output_format 只支持 jpeg / png / webp")

    if target_kb is not None and target_kb <= 0:
        raise HTTPException(status_code=400, detail="target_kb 必须大于 0")

    image_bytes = await file.read()
    original_kb = len(image_bytes) / 1024

    print(
        f"[图片压缩] 文件={filename}, 原始大小={original_kb:.1f}KB, "
        f"目标={target_kb}KB, 最大尺寸={max_width}x{max_height}, 格式={output_format}"
    )

    try:
        compressed_bytes, out_ext = compress_to_target_size(
            image_bytes=image_bytes,
            input_ext=ext,
            target_kb=target_kb,
            max_width=max_width,
            max_height=max_height,
            output_format=output_format,
            strip_exif=strip_exif,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"压缩失败: {str(e)}")

    # 构建输出文件名
    base_name = Path(filename).stem
    output_filename = f"{base_name}_compressed{out_ext}"
    encoded_filename = urllib.parse.quote(output_filename)

    media_type_map = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(out_ext, "application/octet-stream")
    compressed_kb = len(compressed_bytes) / 1024

    print(f"[图片压缩] 压缩完成: {original_kb:.1f}KB -> {compressed_kb:.1f}KB")

    return Response(
        content=compressed_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "X-Original-Size": f"{original_kb:.1f}",
            "X-Compressed-Size": f"{compressed_kb:.1f}",
        }
    )
