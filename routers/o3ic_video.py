import urllib.parse
import tempfile
import os
import shutil
import logging
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from services.ffmpeg_service import parse_lrc, generate_o3ic_video

logger = logging.getLogger(__name__)

router = APIRouter()

ASSETS_DIR = Path(__file__).parent.parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
FONT_FILE = FONTS_DIR / "NotoSansSC-Bold.otf"


@router.post("/o3ic-video/generate")
async def generate_o3ic_video_endpoint(
    audio: UploadFile = File(..., description="音频文件（MP3/WAV/FLAC 等）"),
    lrc: UploadFile = File(..., description="LRC 格式歌词文件"),
    bg_color: str = Form("#000000", description="背景颜色（#RRGGBB）"),
    font_size: int = Form(150, description="歌词字号（px）"),
    sung_color: str = Form("#ff4d4d", description="已唱文字颜色（#RRGGBB），默认红色"),
    unsung_color: str = Form("#ffffff", description="未唱文字颜色（#RRGGBB），默认白色"),
    stroke_color: str = Form("#000000", description="描边颜色（#RRGGBB）"),
    stroke_width: int = Form(2, description="描边宽度（1~8）"),
    resolution: str = Form("1280x720", description="分辨率，建议 1280x720"),
    letter_spacing: int = Form(0, description="字符间距（px），0 为无额外间距"),
    line_gap_ratio: float = Form(1.5, description="行间距倍数（相对于 font_size）"),
    wrap_mode: str = Form("auto", description="换行模式：auto 或 chars"),
    max_chars_per_line: int = Form(11, description="手动换行时每行最大字符数"),
):
    """
    歌词视频合成接口。
    上传音频 + LRC 歌词，生成带卡拉 OK 逐字变色效果的 MP4 视频。
    """
    # 参数校验
    if not any(resolution.lower() == r for r in ["1280x720", "1920x1080", "720x1280", "1080x1920"]):
        parts = resolution.lower().split("x")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise HTTPException(status_code=400, detail="无效的分辨率格式，应为 宽x高，如 1280x720")

    if not (40 <= font_size <= 240):
        raise HTTPException(status_code=400, detail="字号应在 40~240 之间")

    if not (0 <= stroke_width <= 12):
        raise HTTPException(status_code=400, detail="描边宽度应在 0~12 之间")

    # 确定字体路径
    font_path = str(FONT_FILE) if FONT_FILE.exists() else ""
    if not font_path:
        logger.warning("[歌词视频] 内置字体文件不存在，将使用系统默认字体")

    # 字体名（ASS 使用）
    font_name = FONT_FILE.stem if FONT_FILE.exists() else "NotoSansSC-Bold"

    # 创建临时目录
    input_dir = tempfile.mkdtemp(prefix="o3ic_video_in_")

    try:
        # 保存音频
        audio_filename = audio.filename or "audio.mp3"
        audio_path = os.path.join(input_dir, "audio.mp3")
        with open(audio_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)
        logger.info(f"[歌词视频] 已保存音频: {audio_path}")

        # 读取并解析 LRC
        lrc_content = lrc.file.read().decode("utf-8", errors="replace").strip()
        if not lrc_content:
            raise HTTPException(status_code=400, detail="LRC 文件内容为空")
        lrc_lines = parse_lrc(lrc_content)
        if not lrc_lines:
            raise HTTPException(status_code=400, detail="LRC 文件解析失败或歌词为空，请检查文件格式")
        logger.info(f"[歌词视频] 解析到 {len(lrc_lines)} 行歌词")

        # 调用合成服务
        result_path = await generate_o3ic_video(
            audio_path=audio_path,
            lrc_lines=lrc_lines,
            bg_color=bg_color,
            font_size=font_size,
            sung_color=sung_color,
            unsung_color=unsung_color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            resolution=resolution,
            font_path=font_path,
            letter_spacing=letter_spacing,
            line_gap_ratio=line_gap_ratio,
            wrap_mode=wrap_mode,
            max_chars_per_line=max_chars_per_line,
        )

        # 输出文件名
        base_name = Path(audio_filename).stem
        output_filename = f"{base_name}_o3ics_video.mp4"
        encoded_filename = urllib.parse.quote(output_filename)

        def cleanup():
            shutil.rmtree(input_dir, ignore_errors=True)
            if os.path.exists(result_path):
                os.remove(result_path)

        logger.info(f"[歌词视频] 合成完成，返回文件: {result_path}")
        return FileResponse(
            path=result_path,
            filename=output_filename,
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            },
            background=BackgroundTask(cleanup),
        )

    except HTTPException:
        shutil.rmtree(input_dir, ignore_errors=True)
        raise
    except RuntimeError as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        logger.error(f"[歌词视频] 合成失败: {e}")
        raise HTTPException(status_code=500, detail=f"歌词视频合成失败: {e}")
    except Exception as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        logger.error(f"[歌词视频] 合成失败: {e}")
        raise HTTPException(status_code=500, detail=f"歌词视频合成失败: {e}")
