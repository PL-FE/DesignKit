import io
import logging
from PIL import Image, ExifTags

logger = logging.getLogger(__name__)

# 支持的输入格式
SUPPORTED_INPUT_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}

# 输出格式映射（扩展名 -> PIL format name）
OUTPUT_FORMAT_MAP = {
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
}


def _fix_orientation(img: Image.Image) -> Image.Image:
    """根据 EXIF 旋转方向修正图片方向"""
    try:
        exif = img._getexif()  # type: ignore
        if exif is None:
            return img
        orientation_key = next(
            (k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None
        )
        if orientation_key is None or orientation_key not in exif:
            return img
        orientation = exif[orientation_key]
        rotate_map = {3: 180, 6: 270, 8: 90}
        if orientation in rotate_map:
            img = img.rotate(rotate_map[orientation], expand=True)
    except Exception:
        pass
    return img


def _to_rgb_if_needed(img: Image.Image, output_format: str) -> Image.Image:
    """JPEG 不支持 RGBA/P 模式，需要转换"""
    if output_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        return background
    if output_format == "JPEG" and img.mode != "RGB":
        return img.convert("RGB")
    return img


def compress_to_target_size(
    image_bytes: bytes,
    input_ext: str,
    target_kb: float | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
    output_format: str = "jpeg",
    strip_exif: bool = True,
) -> tuple[bytes, str]:
    """
    将图片压缩到指定目标大小（KB），同时支持缩放

    :param image_bytes: 原始图片字节
    :param input_ext: 原始扩展名（如 .jpg）
    :param target_kb: 目标文件大小（KB），None 则不限制大小
    :param max_width: 最大宽度（像素），None 则不限制
    :param max_height: 最大高度（像素），None 则不限制
    :param output_format: 输出格式 'jpeg' / 'png' / 'webp'
    :param strip_exif: 是否清除 EXIF 元数据
    :return: (压缩后字节, 输出文件扩展名)
    """
    pil_format = OUTPUT_FORMAT_MAP.get(output_format.lower(), "JPEG")
    out_ext = f".{output_format.lower()}"
    if out_ext == ".jpeg":
        out_ext = ".jpg"

    img = Image.open(io.BytesIO(image_bytes))

    # 修正方向
    if not strip_exif:
        img = _fix_orientation(img)

    # 缩放（如果指定了最大尺寸）
    if max_width or max_height:
        orig_w, orig_h = img.size
        scale = 1.0
        if max_width and orig_w > max_width:
            scale = min(scale, max_width / orig_w)
        if max_height and orig_h > max_height:
            scale = min(scale, max_height / orig_h)
        if scale < 1.0:
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))
            img = img.resize((new_w, new_h), Image.LANCZOS)
            logger.info(f"缩放: {orig_w}x{orig_h} -> {new_w}x{new_h}")

    img = _to_rgb_if_needed(img, pil_format)

    # PNG 无损，不支持 quality 参数意义不大，直接保存后判断大小
    if pil_format == "PNG":
        buf = io.BytesIO()
        save_kwargs: dict = {"format": pil_format, "optimize": True}
        img.save(buf, **save_kwargs)
        result = buf.getvalue()
        if target_kb and len(result) / 1024 > target_kb:
            logger.warning(
                f"PNG 为无损格式，无法通过质量参数压缩到 {target_kb}KB，"
                f"建议改用 JPEG 或 WebP 格式"
            )
        return result, out_ext

    # JPEG / WebP：用二分法逼近目标大小
    if target_kb is not None:
        target_bytes = int(target_kb * 1024)
        low, high = 10, 95
        best_buf = io.BytesIO()
        # 先用高质量保存，检查是否已经小于目标
        img.save(best_buf, format=pil_format, quality=high, optimize=True)
        if len(best_buf.getvalue()) <= target_bytes:
            logger.info(f"原图已满足目标大小，直接返回高质量结果")
            return best_buf.getvalue(), out_ext

        best_quality = low
        for _ in range(10):  # 最多二分 10 次，精度足够
            mid = (low + high) // 2
            buf = io.BytesIO()
            img.save(buf, format=pil_format, quality=mid, optimize=True)
            size = len(buf.getvalue())
            logger.debug(f"质量={mid}, 大小={size/1024:.1f}KB, 目标={target_kb}KB")
            if size <= target_bytes:
                best_quality = mid
                best_buf = buf
                low = mid + 1
            else:
                high = mid - 1
            if low > high:
                break

        # 如果最低质量仍超目标，返回最低质量结果并记录警告
        if len(best_buf.getvalue()) == 0 or len(best_buf.getvalue()) > target_bytes:
            buf = io.BytesIO()
            img.save(buf, format=pil_format, quality=10, optimize=True)
            best_buf = buf
            logger.warning(
                f"即使最低质量也无法压缩到 {target_kb}KB，"
                f"建议同时设置最大宽高以进一步缩小尺寸"
            )

        logger.info(f"最终质量={best_quality}, 大小={len(best_buf.getvalue())/1024:.1f}KB")
        return best_buf.getvalue(), out_ext

    # 不指定目标大小，使用默认质量 85
    buf = io.BytesIO()
    img.save(buf, format=pil_format, quality=85, optimize=True)
    return buf.getvalue(), out_ext
