import asyncio
import urllib.parse
import os
import re
import shutil
import tempfile
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from services.ffmpeg_service import (
    parse_lrc,
    generate_lyric_video,
    separate_vocals,
)
from services.task_manager import (
    TaskStatus,
    create_task,
    get_task,
    run_background,
    remove_task,
    cleanup_old_tasks,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# 项目内置中文字体路径（思源黑体 Noto Sans SC Bold）
_FONT_PATH = str(Path(__file__).parent.parent / "assets" / "fonts" / "NotoSansSC-Bold.otf")


async def _do_generate(
    task_info,
    audio_path: str,
    audio_filename: str,
    lrc_lines: list[dict],
    bg_color: str,
    background_mode: str,
    font_size: int,
    sung_color: str,
    unsung_color: str,
    stroke_color: str,
    stroke_width: int,
    resolution: str,
    remove_vocals: bool,
    font_path: str,
    letter_spacing: int,
    line_gap_ratio: float,
    wrap_mode: str,
    max_chars_per_line: int,
    input_dir: str,
):
    vocal_removed_path = None
    result_path = None
    try:
        # 1. 如果开启去除人声，先使用 demucs 提取伴奏
        actual_audio = audio_path
        if remove_vocals:
            task_info.progress = 5
            logger.info("[歌词视频] 开始人声分离（demucs）...")
            vocal_removed_path = await separate_vocals(audio_path)
            actual_audio = vocal_removed_path
            logger.info(f"[歌词视频] 人声分离完成: {vocal_removed_path}")

        task_info.progress = 30 if remove_vocals else 10

        # 2. 合成歌词视频
        result_path = await generate_lyric_video(
            audio_path=actual_audio,
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
            background_mode=background_mode,
        )

        # 3. 构造下载文件名
        base_name = Path(audio_filename).stem
        if lrc_lines and lrc_lines[0]["text"]:
            first_line_text = lrc_lines[0]["text"]
            safe_name = re.sub(r'[\\/*?:"<>|]', "", first_line_text).strip()
            if safe_name:
                output_filename = f"{safe_name}.mp4"
            else:
                output_filename = f"{base_name}_lyrics_video.mp4"
        else:
            output_filename = f"{base_name}_lyrics_video.mp4"

        task_info.status = TaskStatus.DONE
        task_info.progress = 100
        task_info.result_path = result_path
        task_info.result_filename = output_filename
        task_info.finished_at = __import__("time").time()
        logger.info(f"[歌词视频] 合成完成: {output_filename}")

    except Exception as e:
        task_info.status = TaskStatus.FAILED
        task_info.error = str(e)
        task_info.finished_at = __import__("time").time()
        # 清理临时文件
        if vocal_removed_path and os.path.exists(vocal_removed_path):
            os.remove(vocal_removed_path)
        if result_path and os.path.exists(result_path):
            os.remove(result_path)
        shutil.rmtree(input_dir, ignore_errors=True)
        logger.error(f"[歌词视频] 合成失败: {str(e)}")


@router.post("/lyric-video/generate")
async def lyric_video_generate_endpoint(
    audio: UploadFile = File(..., description="音频文件（MP3/WAV/FLAC 等）"),
    lrc: UploadFile = File(..., description="LRC 格式歌词文件"),
    bg_color: str = Form("#000000", description="背景颜色（#RRGGBB）"),
    background_mode: str = Form("video", description="背景模式：video 视频背景，image 图片背景，color 纯色背景"),
    font_size: int = Form(150, description="字体大小（px），建议 80~200"),
    sung_color: str = Form("#ff0000", description="已唱部分颜色（#RRGGBB），默认红色"),
    unsung_color: str = Form("#ffffff", description="未唱部分颜色（#RRGGBB），默认白色"),
    stroke_color: str = Form("#000000", description="描边颜色（#RRGGBB）"),
    stroke_width: int = Form(0, description="描边宽度（1~8）"),
    resolution: str = Form("1280x720", description="视频分辨率，建议 1280x720 (720p) 以获得最佳性能，或 1920x1080 (1080p)"),
    remove_vocals: bool = Form(False, description="是否去除人声（使用 AI 伴奏提取，耗时较长）"),
    letter_spacing: int = Form(8, description="字符间距（px），对应 ASS Spacing，0~30"),
    line_gap_ratio: float = Form(1.5, description="行间距倍数（相对于 font_size），建议 1.2~3.0"),
    wrap_mode: str = Form("auto", description="换行模式：auto 自动换行，chars 手动指定每行最大字符数"),
    max_chars_per_line: int = Form(11, description="手动指定每行最大字符数（仅 wrap_mode=chars 时生效）"),
):
    """
    歌词视频合成接口（异步任务模式）。
    上传音频 + LRC 歌词后立即返回 task_id，
    通过 GET /lyric-video/task/{task_id} 轮询进度和下载结果。
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

    if background_mode not in {"video", "image", "color"}:
        raise HTTPException(status_code=400, detail="背景模式无效，应为 video、image 或 color")

    # 检查字体文件是否存在
    if not os.path.exists(_FONT_PATH):
        logger.warning(f"[歌词视频] 内置字体文件不存在: {_FONT_PATH}，将使用系统默认字体")
        font_path = "NotoSansSC-Bold"  # 回退到字体名
    else:
        font_path = _FONT_PATH

    input_dir = tempfile.mkdtemp(prefix="lyric_video_in_")
    audio_filename = audio.filename or "audio.mp3"

    # 1. 保存上传的音频文件
    audio_path = os.path.join(input_dir, audio_filename)
    with open(audio_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)
    logger.info(f"[歌词视频] 已保存音频: {audio_filename}")

    # 2. 读取并解析 LRC 歌词文件
    lrc_content = (await lrc.read()).decode("utf-8", errors="replace")
    lrc_lines = parse_lrc(lrc_content)
    if not lrc_lines:
        shutil.rmtree(input_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="LRC 文件解析失败或歌词为空，请检查文件格式")
    logger.info(f"[歌词视频] 解析到 {len(lrc_lines)} 行歌词")

    # 3. 创建异步任务
    task_info = create_task()
    logger.info(f"[歌词视频] 创建异步任务: {task_info.task_id}")

    asyncio.create_task(run_background(
        task_info,
        _do_generate,
        audio_path=audio_path,
        audio_filename=audio_filename,
        lrc_lines=lrc_lines,
        bg_color=bg_color,
        background_mode=background_mode,
        font_size=font_size,
        sung_color=sung_color,
        unsung_color=unsung_color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        resolution=resolution,
        remove_vocals=remove_vocals,
        font_path=font_path,
        letter_spacing=letter_spacing,
        line_gap_ratio=line_gap_ratio,
        wrap_mode=wrap_mode,
        max_chars_per_line=max_chars_per_line,
        input_dir=input_dir,
    ))

    return JSONResponse({"task_id": task_info.task_id, "status": task_info.status.value})


@router.get("/lyric-video/task/{task_id}")
async def lyric_video_task_status(task_id: str):
    """
    查询异步任务状态。
    - status=processing 时返回进度百分比
    - status=done 时返回文件下载
    - status=failed 时返回错误信息
    """
    task_info = get_task(task_id)
    if not task_info:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    if task_info.status == TaskStatus.DONE and task_info.result_path:
        encoded_filename = urllib.parse.quote(task_info.result_filename)

        def cleanup():
            if task_info.result_path and os.path.exists(task_info.result_path):
                os.remove(task_info.result_path)
            remove_task(task_id)

        return FileResponse(
            path=task_info.result_path,
            filename=task_info.result_filename,
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            },
            background=BackgroundTask(cleanup),
        )

    return JSONResponse(task_info.to_dict())
