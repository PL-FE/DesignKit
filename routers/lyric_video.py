import urllib.parse
import os
import shutil
import tempfile
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from services.ffmpeg_service import (
    parse_lrc,
    generate_lyric_video,
    separate_vocals,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# 项目内置中文字体路径（思源黑体 Noto Sans SC Bold）
_FONT_PATH = str(Path(__file__).parent.parent / "assets" / "fonts" / "NotoSansSC-Bold.otf")


@router.post("/lyric-video/generate")
async def lyric_video_generate_endpoint(
    audio: UploadFile = File(..., description="音频文件（MP3/WAV/FLAC 等）"),
    lrc: UploadFile = File(..., description="LRC 格式歌词文件"),
    bg_color: str = Form("#0a0a1a", description="背景颜色（#RRGGBB）"),
    font_size: int = Form(150, description="字体大小（px），建议 80~200"),
    font_color: str = Form("#ffffff", description="歌词字体颜色（#RRGGBB）"),
    stroke_color: str = Form("#000000", description="描边颜色（#RRGGBB）"),
    stroke_width: int = Form(4, description="描边宽度（1~8）"),
    resolution: str = Form("1920x1080", description="视频分辨率，如 1920x1080 / 1080x1920"),
    remove_vocals: bool = Form(False, description="是否去除人声（使用 AI 伴奏提取，耗时较长）"),
    letter_spacing: int = Form(8, description="字符间距（px），对应 ASS Spacing，0~30"),
    line_gap_ratio: float = Form(1.5, description="行间距倍数（相对于 font_size），建议 1.2~3.0"),
):
    """
    歌词视频合成接口。
    上传音频 + LRC 歌词，生成带大字幕提词的 MP4 视频。
    可选开启人声去除（AI 分离伴奏）。
    """
    # 验证分辨率格式
    try:
        w, h = resolution.lower().split('x')
        int(w), int(h)
    except Exception:
        raise HTTPException(status_code=400, detail="无效的分辨率格式，应为 宽x高，如 1080x1920")

    # 验证字体大小范围
    if not (40 <= font_size <= 240):
        raise HTTPException(status_code=400, detail="字体大小应在 40~240 之间")

    # 验证描边宽度范围
    if not (0 <= stroke_width <= 12):
        raise HTTPException(status_code=400, detail="描边宽度应在 0~12 之间")

    # 检查字体文件是否存在
    if not os.path.exists(_FONT_PATH):
        logger.warning(f"[歌词视频] 内置字体文件不存在: {_FONT_PATH}，将使用系统默认字体")
        font_path = "NotoSansSC-Bold"  # 回退到字体名
    else:
        font_path = _FONT_PATH

    input_dir = tempfile.mkdtemp(prefix="lyric_video_in_")
    audio_filename = audio.filename or "audio.mp3"
    result_path = None
    vocal_removed_path = None

    try:
        # 1. 保存上传的音频文件
        audio_path = os.path.join(input_dir, audio_filename)
        with open(audio_path, "wb") as f:
            shutil.copyfileobj(audio.file, f)
        logger.info(f"[歌词视频] 已保存音频: {audio_filename}")

        # 2. 读取并解析 LRC 歌词文件
        lrc_content = (await lrc.read()).decode("utf-8", errors="replace")
        lrc_lines = parse_lrc(lrc_content)
        if not lrc_lines:
            raise HTTPException(status_code=400, detail="LRC 文件解析失败或歌词为空，请检查文件格式")
        logger.info(f"[歌词视频] 解析到 {len(lrc_lines)} 行歌词")

        # 3. 如果开启去除人声，先使用 demucs 提取伴奏
        actual_audio = audio_path
        if remove_vocals:
            logger.info("[歌词视频] 开始人声分离（demucs）...")
            vocal_removed_path = await separate_vocals(audio_path)
            actual_audio = vocal_removed_path
            logger.info(f"[歌词视频] 人声分离完成: {vocal_removed_path}")

        # 4. 合成歌词视频
        result_path = await generate_lyric_video(
            audio_path=actual_audio,
            lrc_lines=lrc_lines,
            bg_color=bg_color,
            font_size=font_size,
            font_color=font_color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            resolution=resolution,
            font_path=font_path,
            letter_spacing=letter_spacing,
            line_gap_ratio=line_gap_ratio,
        )

        # 5. 构造下载文件名
        base_name = Path(audio_filename).stem
        output_filename = f"{base_name}_lyrics_video.mp4"
        encoded_filename = urllib.parse.quote(output_filename)

        def cleanup():
            shutil.rmtree(input_dir, ignore_errors=True)
            if result_path and os.path.exists(result_path):
                os.remove(result_path)
            if vocal_removed_path and os.path.exists(vocal_removed_path):
                os.remove(vocal_removed_path)

        logger.info(f"[歌词视频] 合成完成，返回文件: {output_filename}")
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
        raise
    except Exception as e:
        shutil.rmtree(input_dir, ignore_errors=True)
        if vocal_removed_path and os.path.exists(vocal_removed_path):
            os.remove(vocal_removed_path)
        if result_path and os.path.exists(result_path):
            os.remove(result_path)
        logger.error(f"[歌词视频] 合成失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"歌词视频合成失败: {str(e)}")
