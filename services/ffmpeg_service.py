import asyncio
import tempfile
import shutil
import logging
import os
import random
from pathlib import Path
import json
import math
import urllib.request

logger = logging.getLogger(__name__)

_LYRIC_BG_VIDEO_PATH = Path("/app/assets/123.mp4") if Path("/app/assets/123.mp4").exists() else Path(__file__).parent.parent / "assets" / "123.mp4"
_LYRIC_BG_IMAGE_URL = "https://picsum.photos/200/300"
_LYRIC_BG_IMAGE_INTERVAL = 10

async def execute_ffprobe(input_path: str) -> dict:
    """
    执行 ffprobe 以获取媒体文件的详细 JSON 信息
    """
    logger.info(f"[FFmpeg] 分析媒体信息: {input_path}")
    
    args = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        input_path
    ]
    
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        logger.error(f"ffprobe 解析失败: {stderr.decode()}")
        raise RuntimeError("无法读取媒体文件信息")
        
    try:
        return json.loads(stdout.decode('utf-8'))
    except json.JSONDecodeError:
        logger.error("ffprobe 返回了无效的 JSON 格式")
        raise RuntimeError("媒体信息解析错误")

async def execute_ffmpeg(input_path: str, args: list[str], output_ext: str, timeout: int = 120) -> str:
    """
    异步调用 ffmpeg 外部命令行工具

    :param input_path: 输入文件路径 (为了记录或日志)
    :param args: ffmpeg 后面的命令参数 (不包含"ffmpeg")，注意需要包含 -y 覆盖以及输出路径
    :param output_ext: 输出文件后缀，例如 ".mp4"
    :param timeout: 超时时间（秒），默认 120 秒
    :return: 临时输出文件路径（调用方负责清理）
    """
    # 让 ffmpeg 将输出直接写在一个专属的临时目录中
    output_dir = tempfile.mkdtemp(prefix="ffmpeg_out_")
    output_file = Path(output_dir) / f"result{output_ext}"
    
    # 构建完整参数
    full_args = ["ffmpeg", "-y"] + args + [str(output_file)]
    
    logger.info(f"[FFmpeg] 执行命令: {' '.join(full_args)}")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *full_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            # 增加超时控制
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
            if process.returncode is None:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
            
            if isinstance(e, asyncio.TimeoutError):
                logger.error(f"ffmpeg 执行超时（超过 {timeout} 秒）: {input_path}")
                raise RuntimeError(f"媒体处理超时（限时 {timeout} 秒）")
            else:
                logger.info(f"ffmpeg 任务被取消: {input_path}")
                raise

        if process.returncode != 0:
            err_msg = stderr.decode()
            logger.error(f"ffmpeg 执行失败: {err_msg}")
            err_lines = [line.strip() for line in err_msg.splitlines() if line.strip()]
            err_excerpt = " | ".join(err_lines[-6:]) if err_lines else "未知 FFmpeg 错误"
            raise RuntimeError(f"媒体处理失败: {err_excerpt}")
            
        if not output_file.exists():
            raise RuntimeError("FFmpeg 执行成功，但并未生成输出文件")
            
        # 复制到独立路径后立刻清理目录
        temp_dest = tempfile.mktemp(suffix=output_ext)
        shutil.copy2(output_file, temp_dest)
        return temp_dest
        
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


async def _download_random_bg_images(audio_duration: float) -> tuple[str, list[str]]:
    image_count = max(1, math.ceil(audio_duration / _LYRIC_BG_IMAGE_INTERVAL))
    image_dir = tempfile.mkdtemp(prefix="lyric_bg_imgs_")
    image_paths: list[str] = []

    async def download_one(index: int) -> str:
        image_path = os.path.join(image_dir, f"bg_{index:03d}.jpg")
        request = urllib.request.Request(
            f"{_LYRIC_BG_IMAGE_URL}?random={random.randint(1, 10_000_000)}_{index}",
            headers={"User-Agent": "DesignKit/1.0"},
        )

        def _fetch() -> str:
            with urllib.request.urlopen(request, timeout=15) as response, open(image_path, "wb") as f:
                shutil.copyfileobj(response, f)
            return image_path

        return await asyncio.to_thread(_fetch)

    try:
        # 并发下载，限制最大并发数为 5
        semaphore = asyncio.Semaphore(5)

        async def limited_download(index: int) -> str:
            async with semaphore:
                return await download_one(index)

        results = await asyncio.gather(*[limited_download(i) for i in range(image_count)])
        image_paths.extend(results)
        return image_dir, image_paths
    except Exception:
        shutil.rmtree(image_dir, ignore_errors=True)
        raise


def _build_image_concat_file(image_paths: list[str], audio_duration: float) -> str:
    concat_file = tempfile.mktemp(suffix=".txt")
    segment_duration = _LYRIC_BG_IMAGE_INTERVAL

    with open(concat_file, "w", encoding="utf-8") as f:
        for image_path in image_paths:
            escaped_path = image_path.replace("'", "'\\''").replace('\\', '/')
            f.write(f"file '{escaped_path}'\n")
            f.write(f"duration {segment_duration}\n")

        last_image_path = image_paths[-1].replace("'", "'\\''").replace('\\', '/')
        f.write(f"file '{last_image_path}'\n")

    return concat_file


def _build_subtitle_filter(escaped_ass: str, escaped_fontsdir: str) -> str:
    return f"subtitles='{escaped_ass}':fontsdir='{escaped_fontsdir}'"


def _build_cover_filter(width: str, height: str) -> str:
    return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=20"


def _build_dimmed_cover_filter(width: str, height: str, escaped_ass: str, escaped_fontsdir: str) -> str:
    subtitle_filter = _build_subtitle_filter(escaped_ass, escaped_fontsdir)
    return (
        f"{_build_cover_filter(width, height)},"
        f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.42:t=fill,"
        f"{subtitle_filter}"
    )


def _darken_hex_color(hex_color: str, factor: float = 0.06) -> str:
    """Darken a hex color by factor (0-1), preserving hue for subtle ambient tint."""
    h = hex_color.replace("0x", "").replace("#", "")
    r = int(int(h[0:2], 16) * factor)
    g = int(int(h[2:4], 16) * factor)
    b = int(int(h[4:6], 16) * factor)
    return f"0x{r:02x}{g:02x}{b:02x}"


def _build_glow_background_source(width: str, height: str, ffmpeg_bg_color: str) -> str:
    """Tech-themed dynamic glow background — optimized for speed with large, heavily blurred orbs."""
    dark_base = _darken_hex_color(ffmpeg_bg_color)
    return (
        f"color=c={dark_base}:size={width}x{height}:rate=12,"
        f"format=rgba,"
        # Orb 1: Cyan, slow drift, top-left
        f"drawbox=x='iw*0.10+sin(t*0.7)*iw*0.08':y='ih*0.12+cos(t*0.6)*ih*0.08':w='iw*0.40':h='ih*0.40':color=0x00e5ff@0.16:t=fill,"
        # Orb 2: Magenta, wide orbit, center-right
        f"drawbox=x='iw*0.48+cos(t*0.55)*iw*0.10':y='ih*0.30+sin(t*0.7)*ih*0.10':w='iw*0.38':h='ih*0.38':color=0xe040fb@0.14:t=fill,"
        # Orb 3: Purple, bottom-center
        f"drawbox=x='iw*0.22+cos(t*0.8)*iw*0.12':y='ih*0.48+sin(t*0.45)*ih*0.08':w='iw*0.42':h='ih*0.42':color=0x7c4dff@0.13:t=fill,"
        # Orb 4: Electric blue, fast cross-motion, top-right
        f"drawbox=x='iw*0.55+cos(t*1.0)*iw*0.08':y='ih*0.10+sin(t*0.9)*ih*0.08':w='iw*0.28':h='ih*0.28':color=0x448aff@0.15:t=fill,"
        # Orb 5: Teal accent, bottom-left
        f"drawbox=x='iw*0.05+sin(t*0.4)*iw*0.10':y='ih*0.55+cos(t*0.65)*ih*0.08':w='iw*0.36':h='ih*0.36':color=0x1de9b6@0.12:t=fill,"
        # Heavy Gaussian blur for bokeh glow
        f"gblur=sigma=48:steps=2,"
        f"format=yuv420p"
    )


def _build_glow_background_filter(escaped_ass: str, escaped_fontsdir: str) -> str:
    subtitle_filter = _build_subtitle_filter(escaped_ass, escaped_fontsdir)
    return f"eq=brightness=-0.02:saturation=1.15,{subtitle_filter}"


def _build_solid_background_filter(escaped_ass: str, escaped_fontsdir: str) -> str:
    return _build_subtitle_filter(escaped_ass, escaped_fontsdir)

async def convert_format(input_path: str, target_format: str) -> str:
    """
    格式转换
    """
    target_format = target_format.lower()
    
    # 构建基础参数
    args = ["-i", input_path]
    
    # 纯音频提取：如果目标是 mp3/aac/wav 等，可以去掉视频流 (vn)
    if target_format in ["mp3", "aac", "wav"]:
        args.extend(["-vn"])
        # mp3 特殊质量控制（默认使用较高比特率或 VBR 质量 2）
        if target_format == "mp3":
            args.extend(["-q:a", "2"])
            
    # 如果是视频互转，且仅仅是换一个壳子（例如 mkv -> mp4），我们尝试先拷贝流？
    # 为了保证不出错和最广泛的通用性，这里先做一次安全的重新编码
    # 或者对于高质量诉求，可以添加:
    if target_format in ["mp4", "mov", "mkv"]:
        args.extend(["-c:v", "libx264", "-c:a", "aac", "-preset", "fast"])
        
    return await execute_ffmpeg(input_path, args, f".{target_format}")

async def compress_video(input_path: str, level: str) -> str:
    """
    智能体积压缩 (以 mp4/h264 输出为主)
    """
    level = level.lower()
    
    # 构建基础参数 (只处理视频压缩，音频统一用 aac 128k 保证基本质量即可)
    args = ["-i", input_path]
    
    # H.264 编码，兼顾速度与质量
    args.extend(["-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-b:a", "128k"])
    
    # 按照选择的等级分配 CRF（Constant Rate Factor）质量系数
    # CRF 值越大数据越小，画质越差。一般高质量选 18-23，中等 24-28，极高压缩 29-33
    if level == "high":
        # 强力压缩：高损失、极简体积 (可能伴随降级 720p 操作)
        args.extend(["-crf", "32", "-vf", "scale=-2:720"])
    elif level == "low":
        # 轻微压缩：低损失、类似原画
        args.extend(["-crf", "22"])
    else:  # medium
        # 均衡压缩：常规网站上传限制的选择
        args.extend(["-crf", "26"])
        
    # 强制统一输出为 .mp4 后缀，因为它是网页与设备最通用的最终格式
    return await execute_ffmpeg(input_path, args, ".mp4")

async def make_gif(input_path: str, start_time: str, duration: str, fps: int, output_fmt: str) -> str:
    """
    制作动图或截图：支持 GIF/WEBP 动图，或 JPG 提纯一张图。
    """
    args = []
    
    # -ss 如果放在 -i 之前会快很多（快速跳跃），只有非常精确的要求才放在 -i 之后
    # 为了速度考虑，放 -i 前面进行近似快速 seeking
    if start_time and start_time != "0":
        args.extend(["-ss", start_time])
        
    args.extend(["-i", input_path])
    
    # 截图一张
    if output_fmt == "jpg":
        args.extend(["-vframes", "1", "-q:v", "2"])
        return await execute_ffmpeg(input_path, args, ".jpg")
        
    # 如果是动图，则需要持续时长及帧率缩放
    if duration and duration != "0":
        args.extend(["-t", duration])
        
    # 为了减少体积，动图通常我们需要限制最大宽度和 fps
    # 宽度最大限制为 480px（兼顾清晰和体积），高度自动按比例缩放，并配合 fps 控制
    vf_str = f"fps={fps},scale=480:-1:flags=lanczos"
    
    if output_fmt == "gif":
        # GIF 为了缩减体积，采用定制滤镜：
        # max_colors=128：减半色阶；bayer 抖动：增强压缩率和渐变表现
        vf_str += ",split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
        args.extend(["-vf", vf_str, "-loop", "0"]) # 0=无限循环
        
    elif output_fmt == "webp":
        # 动图 WebP 体积更小，边缘更锐利
        args.extend(["-vf", vf_str, "-loop", "0", "-c:v", "libwebp", "-lossless", "0", "-qscale", "70", "-preset", "icon"])
        
    return await execute_ffmpeg(input_path, args, f".{output_fmt}")

async def edit_video(input_path: str, params: dict) -> str:
    """
    多种编辑效果拼装
    params = {
        "trim_start": str,
        "trim_end": str,
        "crop": str,
        "remove_audio": bool,
        "speed": float,
    }
    """
    args = []
    
    start = params.get("trim_start", "0")
    if start and start != "0":
        args.extend(["-ss", start])
        
    args.extend(["-i", input_path])
    
    end = params.get("trim_end", "")
    if end and end != "0":
        args.extend(["-to", end])
        
    vf_filters = []
    af_filters = []
    
    crop = params.get("crop", "")
    if crop:
        # e.g., "iw/2:ih/2:0:0"
        vf_filters.append(f"crop={crop}")
        
    speed = params.get("speed", 1.0)
    if speed != 1.0:
        # 视频变速倍率倒数机制 (setpts=0.5*PTS 等于 2倍速)
        vf_filters.append(f"setpts={1/speed}*PTS")
        # 音频需要用 atempo，由于 atempo 限制在 0.5 到 2.0，超过需要串联，我们目前简化直接给一次
        # 有些边界值支持到 0.5 甚至更广（某些 FFmpeg 版本支持到 0.5~100）
        af_filters.append(f"atempo={speed}")
        
    if vf_filters:
        args.extend(["-vf", ",".join(vf_filters)])
        
    if params.get("remove_audio", False):
        args.append("-an")
    elif af_filters:
        args.extend(["-af", ",".join(af_filters)])
        
    # 为了兼容所有的滤镜和剪辑并尽可能保证速度不掉，这里可以重编码并设定 medium/fast preset
    args.extend(["-c:v", "libx264", "-preset", "fast", "-c:a", "aac"])
    
    return await execute_ffmpeg(input_path, args, ".mp4")

async def separate_vocals(input_path: str) -> str:
    """
    使用 demucs 进行人声分离，提取伴奏
    """
    logger.info(f"[Demucs] 开始分离人声: {input_path}")
    
    # 再次尝试通过环境变量关闭 SSL（这会影响 torch.hub 的下载）
    env = os.environ.copy()
    env["PYTHONHTTPSVERIFY"] = "0"
    env["CURL_CA_BUNDLE"] = ""
    env["SSL_CERT_FILE"] = ""
    # 限制 torch CPU 线程数，避免吃满所有核心导致其他进程卡死
    env["OMP_NUM_THREADS"] = "2"
    env["MKL_NUM_THREADS"] = "2"
    env["TORCH_NUM_THREADS"] = "2"

    # 创建输出目录
    output_dir = tempfile.mkdtemp(prefix="demucs_out_")
    
    # 执行 demucs 命令
    # 核心修复：通过 python -c 注入 SSL 绕过代码，确保子进程下载模型时跳过证书校验
    # 使用 sys.argv 仿真命令行参数传递
    python_cmd = (
        "import ssl, sys; "
        "ssl._create_default_https_context = ssl._create_unverified_context; "
        "from demucs.separate import main; "
        "sys.argv = ['demucs'] + sys.argv[1:]; "
        "main()"
    )
    
    args = [
        "python3", "-c", python_cmd,
        "-n", "htdemucs",
        "--two-stems", "vocals",
        "--mp3",
        "-o", output_dir,
        input_path
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
        try:
            # 增加 300 秒超时控制
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)
        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
            if process.returncode is None:
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
            
            if isinstance(e, asyncio.TimeoutError):
                logger.error("demucs 执行超时（超过 300 秒）")
                raise RuntimeError("人声分离超时（限时 300 秒），请尝试较短的音频")
            else:
                logger.info("demucs 任务被取消")
                raise

        if process.returncode != 0:
            err_output = stderr.decode()
            logger.error(f"demucs 执行失败 (code {process.returncode}): {err_output}")
            # 如果是因为缺少某些 ffmpeg 编码器导致 mp3 失败，尝试不加 --mp3 再跑一次（默认 wav）
            if "not found" in err_output.lower() or "encoder" in err_output.lower():
                logger.info("[Demucs] 尝试退回到 wav 模式重试...")
                args.remove("--mp3")
                process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await process.communicate()
                if process.returncode != 0:
                     raise RuntimeError(f"人声分离重试失败: {stderr.decode()}")
            else:
                raise RuntimeError(f"人声分离失败: {err_output}")
            
        # demucs 的输出路径通常是: output_dir/htdemucs/input_filename/no_vocals.mp3 (或 .wav)
        input_filename_stem = Path(input_path).stem
        # 递归查找结果文件，因为不同版本或不同模型的子目录可能略有差异
        result_files = list(Path(output_dir).rglob("no_vocals.*"))
        
        if not result_files:
            logger.error(f"Demucs 输出目录内容: {list(Path(output_dir).rglob('*'))}")
            raise RuntimeError("人声分离成功完成，但未在输出目录找到结果文件")
            
        result_path = result_files[0]
        ext = result_path.suffix
                
        # 复制到独立路径后立刻清理目录
        temp_dest = tempfile.mktemp(suffix=ext)
        shutil.copy2(result_path, temp_dest)
        return temp_dest
        
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)

def parse_lrc(lrc_content: str) -> list[dict]:
    """
    解析 LRC 格式歌词文件，返回时间戳和歌词对的列表。
    支持两种格式：
      1. 标准格式：[mm:ss.xx] 歌词文字
      2. 逐字格式：[mm:ss.xx]字[mm:ss.xx]字…（每个字单独时间标签）
    返回: [{"time": float（秒）, "text": str}]
    """
    import re

    lines = []

    for raw_line in lrc_content.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        tags = re.findall(r'\[(\d{1,3}):(\d{2})\.(\d{1,3})\]', raw_line)
        if not tags:
            continue

        # 检测是否为增强型 LRC (<time> 标签)
        enhanced_tags = re.findall(r'<(\d{1,3}):(\d{2})\.(\d{1,3})>', raw_line)

        if enhanced_tags:
            # 增强型格式：提取纯文本和所有时间戳
            full_text = re.sub(r'\[.*?\]|<.*?>', '', raw_line)
            char_times = []
            for m, s, cs in enhanced_tags:
                total_seconds = int(m) * 60 + int(s) + int(cs.ljust(3, '0')[:3]) / 1000.0
                char_times.append(total_seconds)
            
            if not full_text:
                continue
                
            for _m, _s, _cs in tags:
                lines.append({
                    "time": char_times[0],
                    "text": full_text,
                    "char_times": char_times,
                })
        else:
            plain_text = re.sub(r'\[\d{1,3}:\d{2}\.\d{1,3}\]', '', raw_line).strip()
            if not plain_text:
                continue

            # 检测逐字LRC：标签数量接近文本长度（>=60%），说明每个字都有独立的[time]标签
            is_per_char = len(tags) >= len(plain_text) * 0.6

            if is_per_char:
                # 逐字格式：提取每个 (时间标签, 紧跟文字) 对
                pairs = re.findall(r'\[(\d{1,3}):(\d{2})\.(\d{1,3})\]([^\[]*)', raw_line)
                chars: list[str] = []
                char_times: list[float] = []
                for m, s, cs, ch in pairs:
                    ch = ch.strip()
                    if ch:
                        chars.append(ch)
                        total_seconds = int(m) * 60 + int(s) + int(cs.ljust(3, '0')[:3]) / 1000.0
                        char_times.append(total_seconds)
                if not chars:
                    continue
                full_text = ''.join(chars)
                lines.append({
                    "time": char_times[0],
                    "text": full_text,
                    "char_times": char_times,
                })
            else:
                # 标准格式：多个时间标签共享同一行歌词
                for m, s, cs in tags:
                    minutes = int(m)
                    seconds = int(s)
                    centiseconds_str = cs.ljust(3, '0')[:3]
                    milliseconds = int(centiseconds_str)
                    total_seconds = minutes * 60 + seconds + milliseconds / 1000.0
                    lines.append({"time": total_seconds, "text": plain_text})

    # 按时间排序
    lines.sort(key=lambda x: x["time"])

    # 过滤相同时间的歌词
    unique_lines = []
    first_group_time = lines[0]["time"] if lines else None
    for line in lines:
        if unique_lines and abs(line["time"] - unique_lines[-1]["time"]) < 0.1:
            if first_group_time is not None and abs(line["time"] - first_group_time) < 0.1:
                continue
            else:
                unique_lines[-1] = line
        else:
            unique_lines.append(line)
            
    return unique_lines


def _seconds_to_ass_time(seconds: float) -> str:
    """将浮点秒数转换为 ASS 字幕时间格式 H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _lrc_to_ass(
    lrc_lines: list[dict],
    audio_duration: float,
    font_name: str,
    font_size: int,
    sung_color: str,
    unsung_color: str,
    stroke_color: str,
    stroke_width: int,
    resolution: str,
    letter_spacing: int = 0,
    line_gap_ratio: float = 1.5,
    wrap_mode: str = "auto",
    max_chars_per_line: int = 11,
    lines_mode: str = "3",
    cover_title: str = "",
    cover_subtitle: str = "",
    cover_title_font_size: int = 120,
    cover_subtitle_font_size: int = 80,
) -> str:
    """
    将 LRC 歌词转换为 ASS 字幕，实现卡拉 OK 逐字变色效果。

    三行滚动模式（lines_mode="3"）：
      - 上一行（上方）：已唱完，显示已唱颜色，全行同时变色
      - 当前行（中间）：卡拉 OK 效果，未唱→已唱逐字变色
      - 下一行（下方）：未唱，显示未唱颜色（更淡）

    两行居中模式（lines_mode="2"）：
      - 第一行（上方）：当前歌词，卡拉 OK 效果
      - 第二行（下方）：下一句歌词，静态显示未唱颜色
      - 两行相同大小，颜色不同（已唱/未唱）
      - 第一行唱完后保持在上方（已唱颜色），第二行在下方开始唱
      - 两行都唱完后一起消失，切换到下两行
    """
    def hex_to_ass_color(hex_color: str, alpha: str = "00") -> str:
        """#RRGGBB → ASS &HAABBGGRR"""
        h = hex_color.lstrip('#')
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H{alpha}{b}{g}{r}"

    width, height = map(int, resolution.lower().split('x'))
    cx = width // 2
    cy = height // 2

    # ASS 颜色值（ASS格式：&HAABBGGRR，alpha=00表示完全不透明）
    sung_ass   = hex_to_ass_color(sung_color,   "00")  # 已唱颜色
    unsung_ass = hex_to_ass_color(unsung_color, "00")  # 未唱颜色
    outline_ass = hex_to_ass_color(stroke_color, "00")  # 描边颜色

    # 三行模式：上下行使用灰色
    gray_ass = hex_to_ass_color("#aaaaaa", "00")
    dim_outline_ass = hex_to_ass_color(stroke_color, "00")

    # 上下行字号为当前行的 68%
    dim_size = max(36, int(font_size * 0.68))
    dim_stroke = max(1, stroke_width - 1)

    # 行间距计算
    sentence_gap = int(font_size * line_gap_ratio)
    margin_lr = int(width * 0.03)

    # 淡入淡出时长（毫秒）
    anim_in_ms = 300
    fade_out_ms = 150
    dim_fade_ms = 250

    # 根据行数模式选择样式配置
    if lines_mode == "2":
        # 两行居中模式：第一行已唱颜色，第二行未唱颜色
        top_ass = sung_ass   # 第一行（当前）：卡拉OK效果
        bottom_ass = unsung_ass  # 第二行（下一句）：未唱颜色
        dim_ass = unsung_ass
        # 两行使用相同字号
        top_size = font_size
        bottom_size = font_size
        dim_outline = outline_ass
    else:
        # 三行滚动模式：上下行使用灰色
        top_ass = sung_ass
        bottom_ass = unsung_ass
        dim_ass = gray_ass
        # 上下行字号为当前行的 68%
        top_size = dim_size
        bottom_size = dim_size
        dim_outline = dim_outline_ass

    # ASS 基础样式（Default 用于当前行卡拉 OK，Dim 用于上下行，CoverTitle/CoverSubtitle 用于封面文字）
    # 注意: MarginL 和 MarginR 必须设置以启用 ASS 原生智能自动换行！
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{sung_ass},{unsung_ass},{outline_ass},&H80000000,-1,0,0,0,100,100,0,0,1,{stroke_width},2,5,{margin_lr},{margin_lr},0,1
Style: Dim,{font_name},{dim_size},{gray_ass},{gray_ass},{dim_outline_ass},&H80000000,0,0,0,0,100,100,0,0,1,{dim_stroke},2,5,{margin_lr},{margin_lr},0,1
Style: Prev,{font_name},{dim_size},{gray_ass},{gray_ass},{dim_outline_ass},&H80000000,0,0,0,0,100,100,0,0,1,{dim_stroke},2,5,{margin_lr},{margin_lr},0,1
Style: Top2Line,{font_name},{top_size},{top_ass},{top_ass},{dim_outline},&H80000000,-1,0,0,0,100,100,0,0,1,{stroke_width},2,5,{margin_lr},{margin_lr},0,1
Style: Bottom2Line,{font_name},{bottom_size},{bottom_ass},{bottom_ass},{dim_outline},&H80000000,-1,0,0,0,100,100,0,0,1,{stroke_width},2,5,{margin_lr},{margin_lr},0,1
Style: CoverTitle,{font_name},{cover_title_font_size},{sung_ass},{unsung_ass},{outline_ass},&H80000000,-1,0,0,0,100,100,{letter_spacing},0,1,{stroke_width},2,5,{margin_lr},{margin_lr},0,1
Style: CoverSubtitle,{font_name},{cover_subtitle_font_size},{unsung_ass},{unsung_ass},{outline_ass},&H80000000,0,0,0,0,100,100,{letter_spacing},0,1,{stroke_width},2,5,{margin_lr},{margin_lr},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def escape(text: str) -> str:
        """转义 ASS 特殊字符"""
        return text.replace("\\", "\\\\").replace("{", "\\{")

    def build_karaoke_text(text: str, line_start: float, line_end: float, char_times: list[float] | None = None) -> str:
        if not text: return ""
        k_cs = []
        total_chars = len(text)
        if char_times and len(char_times) >= total_chars:
            for j in range(total_chars):
                c_start = char_times[j]
                c_end = char_times[j+1] if j+1 < len(char_times) else line_end
                k_cs.append(max(1, int(round((c_end - c_start) * 100))))
        else:
            total_cs = int(round((line_end - line_start) * 100))
            if total_chars > 0:
                per_char_cs = max(1, total_cs // total_chars)
                k_cs = [per_char_cs] * total_chars
                k_cs[-1] += (total_cs - sum(k_cs))
        
        segment = ""
        char_count = 0
        limit = max_chars_per_line if max_chars_per_line > 0 else 11
        for j, ch in enumerate(text):
            if wrap_mode == "chars" and char_count >= limit:
                segment += "\\N"
                char_count = 0
            segment += f"{{\\kf{k_cs[j]}}}{escape(ch)}"
            char_count += 1
        return segment

    def format_plain_text(text: str) -> str:
        if wrap_mode == "chars":
            limit = max_chars_per_line if max_chars_per_line > 0 else 11
            res = ""
            char_count = 0
            for i, ch in enumerate(text):
                if char_count >= limit:
                    res += "\\N"
                    char_count = 0
                res += escape(ch)
                char_count += 1
            return res
        return escape(text)

    events: list[str] = []

    # 封面文字帧（自定义标题和副标题，显示在歌词之前）
    if cover_title or cover_subtitle:
        logger.info(f"[ASS字幕] 生成封面文字: title='{cover_title}', subtitle='{cover_subtitle}'")
        first_lyric_time = lrc_lines[0]["time"] if lrc_lines and len(lrc_lines) > 0 else 3.0
        cover_duration = max(2.0, min(first_lyric_time, 5.0))
        cover_end_time = cover_duration
        
        cover_start = _seconds_to_ass_time(0.0)
        cover_end = _seconds_to_ass_time(cover_end_time)
        
        if cover_title:
            title_y = cy - int(cover_title_font_size * 0.8) if cover_subtitle else cy
            title_tag = f"{{\\an5\\pos({cx},{title_y})\\fad(0,500)}}"
            title_display = format_plain_text(cover_title)
            events.append(f"Dialogue: 5,{cover_start},{cover_end},CoverTitle,,0,0,0,,{title_tag}{title_display}")
        
        if cover_subtitle:
            subtitle_y = cy + int(cover_title_font_size * 0.5) if cover_title else cy
            subtitle_tag = f"{{\\an5\\pos({cx},{subtitle_y})\\fad(0,500)}}"
            subtitle_display = format_plain_text(cover_subtitle)
            events.append(f"Dialogue: 4,{cover_start},{cover_end},CoverSubtitle,,0,0,0,,{subtitle_tag}{subtitle_display}")

    # 主体歌词行
    for i, line in enumerate(lrc_lines):
        start = line["time"]
        end = lrc_lines[i + 1]["time"] if i + 1 < len(lrc_lines) else audio_duration
        if end <= start:
            end = start + 0.5
        line_duration = end - start

        s = _seconds_to_ass_time(start)
        e = _seconds_to_ass_time(end)

        k_text = build_karaoke_text(line["text"], start, end, line.get("char_times", []))

        if lines_mode == "2":
            if i % 2 == 0:
                next_i = i + 1
                if next_i < len(lrc_lines):
                    next_line = lrc_lines[next_i]
                    next_start = next_line["time"]
                    next_end = lrc_lines[next_i + 1]["time"] if next_i + 1 < len(lrc_lines) else audio_duration
                    if next_end <= next_start:
                        next_end = next_start + 0.5
                    
                    k_text_next = build_karaoke_text(next_line["text"], next_start, next_end, next_line.get("char_times", []))
                    
                    ns = _seconds_to_ass_time(next_start)
                    ne = _seconds_to_ass_time(next_end)
                    
                    plain_curr = format_plain_text(line["text"])
                    plain_next = format_plain_text(next_line["text"])
                    
                    y_top = cy - sentence_gap // 2
                    y_bot = cy + sentence_gap // 2
                    
                    tag_top_a = f"{{\\an5\\pos({cx},{y_top})\\fad({anim_in_ms if i>0 else 0},0)}}"
                    events.append(f"Dialogue: 2,{s},{e},Default,,0,0,0,,{tag_top_a}{k_text}")
                    
                    tag_bot_a = f"{{\\an5\\pos({cx},{y_bot})\\fad({anim_in_ms},0)}}"
                    events.append(f"Dialogue: 0,{s},{ns},Bottom2Line,,0,0,0,,{tag_bot_a}{plain_next}")
                    
                    tag_top_b = f"{{\\an5\\pos({cx},{y_top})\\fad(0,0)}}"
                    events.append(f"Dialogue: 1,{e},{ne},Top2Line,,0,0,0,,{tag_top_b}{plain_curr}")
                    
                    tag_bot_b = f"{{\\an5\\pos({cx},{y_bot})\\fad(0,0)}}"
                    events.append(f"Dialogue: 2,{ns},{ne},Default,,0,0,0,,{tag_bot_b}{k_text_next}")
                else:
                    tag = f"{{\\an5\\pos({cx},{cy - sentence_gap // 2})\\fad({anim_in_ms if i>0 else 0},{fade_out_ms})}}"
                    events.append(f"Dialogue: 2,{s},{e},Default,,0,0,0,,{tag}{k_text}")
        else:
            tag = f"{{\\an5\\pos({cx},{cy})\\fad({anim_in_ms if i>0 else 0},{fade_out_ms})}}"
            events.append(f"Dialogue: 2,{s},{e},Default,,0,0,0,,{tag}{k_text}")
            
            if i > 0:
                plain_prev = format_plain_text(lrc_lines[i-1]["text"])
                tag_prev = f"{{\\an5\\pos({cx},{cy - sentence_gap})\\fad({dim_fade_ms if i>1 else 0},0)}}"
                events.append(f"Dialogue: 1,{s},{e},Prev,,0,0,0,,{tag_prev}{plain_prev}")
                
            if i + 1 < len(lrc_lines):
                plain_next = format_plain_text(lrc_lines[i+1]["text"])
                tag_next = f"{{\\an5\\pos({cx},{cy + sentence_gap})\\fad({dim_fade_ms if i>0 else 0},0)}}"
                events.append(f"Dialogue: 0,{s},{e},Dim,,0,0,0,,{tag_next}{plain_next}")

    return header + "\n".join(events) + "\n"






async def generate_lyric_video(
    audio_path: str,
    lrc_lines: list[dict],
    bg_color: str,
    font_size: int,
    sung_color: str,
    unsung_color: str,
    stroke_color: str,
    stroke_width: int,
    resolution: str,
    font_path: str,
    letter_spacing: int = 2,
    line_gap_ratio: float = 1.8,
    wrap_mode: str = "auto",
    max_chars_per_line: int = 11,
    background_mode: str = "video",
    lines_mode: str = "3",
    cover_title: str = "",
    cover_subtitle: str = "",
    cover_title_font_size: int = 120,
    cover_subtitle_font_size: int = 80,
) -> str:
    """
    使用 FFmpeg 将音频和解析后的 LRC 歌词合成为带字幕的 MP4 视频。

    流程：
    1. 通过 ffprobe 获取音频时长
    2. 将 lrc_lines 转换为 ASS 字幕文件（临时文件）
    3. FFmpeg 生成纯色背景 + 叠加字幕 + 合并音频

    返回临时输出 mp4 文件路径
    """
    logger.info(f"[歌词视频] 开始合成，音频: {audio_path}, 歌词行数: {len(lrc_lines)}, 分辨率: {resolution}, 行数模式: {lines_mode}")

    # 1. 获取音频时长
    probe_data = await execute_ffprobe(audio_path)
    audio_duration = float(probe_data.get("format", {}).get("duration", 0))
    if audio_duration <= 0:
        raise RuntimeError("无法读取音频时长，请检查文件格式")
    logger.info(f"[歌词视频] 音频时长: {audio_duration:.2f}s")

    # 静音时长（封面 2 秒）
    silence_duration = 2.0
    
    # 1. 生成 4 秒静音音频并与原音频拼接
    silence_file = None
    try:
        # 生成静音音频
        silence_args = [
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(silence_duration),
            "-c:a", "libmp3lame",
            "-q:a", "2"
        ]
        silence_file = await execute_ffmpeg(audio_path, silence_args, ".mp3")
        
        # 使用 filter_complex 拼接静音和原音频
        concat_args = [
            "-i", silence_file,
            "-i", audio_path,
            "-filter_complex",
            "[0:a][1:a]concat=n=2:v=0:a=1[outa]",
            "-map", "[outa]",
            "-c:a", "libmp3lame",
            "-q:a", "2"
        ]
        audio_with_silence = await execute_ffmpeg("concat_audio", concat_args, ".mp3")
        # 更新音频路径用于后续合成
        audio_path = audio_with_silence
        
        # 更新音频时长
        audio_duration = audio_duration + silence_duration
        logger.info(f"[歌词视频] 已拼接 {silence_duration}s 静音音频，总时长: {audio_duration:.2f}s")
    finally:
        if os.path.exists(silence_file):
            os.remove(silence_file)

    # 2. 提取字体名
    font_name = Path(font_path).stem

    # 3. 生成 ASS 字幕内容（卡拉 OK 逐字变色）
    # 注意：歌词时间戳需要偏移 silence_duration 秒
    lrc_lines_offset = []
    for line in lrc_lines:
        new_line = line.copy()
        new_line["time"] += silence_duration
        if "char_times" in line:
            new_line["char_times"] = [t + silence_duration for t in line["char_times"]]
        lrc_lines_offset.append(new_line)
    ass_content = _lrc_to_ass(
        lrc_lines=lrc_lines_offset,
        audio_duration=audio_duration,
        font_name=font_name,
        font_size=font_size,
        sung_color=sung_color,
        unsung_color=unsung_color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        resolution=resolution,
        letter_spacing=letter_spacing,
        line_gap_ratio=line_gap_ratio,
        wrap_mode=wrap_mode,
        max_chars_per_line=max_chars_per_line,
        lines_mode=lines_mode,
        cover_title=cover_title,
        cover_subtitle=cover_subtitle,
        cover_title_font_size=cover_title_font_size,
        cover_subtitle_font_size=cover_subtitle_font_size,
    )

    # 4. 写入临时 ASS 文件
    ass_file = tempfile.mktemp(suffix=".ass")
    with open(ass_file, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    logger.info(f"[歌词视频] 已生成 ASS 字幕: {ass_file}")
    # 输出封面相关的事件行，便于调试
    cover_events = [line for line in ass_content.split('\n') if line.startswith('Dialogue:') and ('CoverTitle' in line or 'CoverSubtitle' in line)]
    if cover_events:
        logger.info(f"[歌词视频] 封面事件行: {cover_events}")
    else:
        logger.warning("[歌词视频] 未找到封面事件行！cover_title='%s', cover_subtitle='%s'", cover_title, cover_subtitle)

    # 5. 解析分辨率
    width, height = resolution.lower().split('x')

    # 6. 处理背景颜色（#RRGGBB → FFmpeg color=0xRRGGBB）
    bg_hex = bg_color.lstrip('#')
    ffmpeg_bg_color = f"0x{bg_hex}"

    bg_video_path = _LYRIC_BG_VIDEO_PATH
    use_bg_video = bg_video_path.exists()
    bg_video_duration = 0.0
    bg_seek_start = 0.0
    bg_image_dir = None
    bg_image_paths: list[str] = []
    bg_image_concat_file = None
    normalized_background_mode = (background_mode or "video").lower()
    use_bg_image = False

    if normalized_background_mode not in {"video", "image", "color"}:
        normalized_background_mode = "video"

    if normalized_background_mode == "video" and use_bg_video:
        try:
            bg_probe_data = await execute_ffprobe(str(bg_video_path))
            bg_video_duration = float(bg_probe_data.get("format", {}).get("duration", 0))
            if bg_video_duration <= 0:
                logger.warning(f"[歌词视频] 背景视频时长无效，回退纯色背景: {bg_video_path}")
                use_bg_video = False
            else:
                max_seek_start = max(0.0, bg_video_duration - audio_duration)
                bg_seek_start = random.uniform(0.0, max_seek_start) if max_seek_start > 0 else 0.0
                logger.info(
                    f"[歌词视频] 使用背景视频: {bg_video_path}, 时长: {bg_video_duration:.2f}s, "
                    f"随机截取起点: {bg_seek_start:.2f}s"
                )
        except Exception as e:
            logger.warning(f"[歌词视频] 背景视频不可用，回退纯色背景: {bg_video_path}, 原因: {str(e)}")
            use_bg_video = False
    else:
        use_bg_video = False

    if normalized_background_mode in {"video", "image"} and not use_bg_video:
        try:
            bg_image_dir, bg_image_paths = await _download_random_bg_images(audio_duration)
            bg_image_concat_file = _build_image_concat_file(bg_image_paths, audio_duration)
            use_bg_image = True
            logger.info(f"[歌词视频] 已下载 {len(bg_image_paths)} 张背景图用于轮播背景")
        except Exception as e:
            logger.warning(f"[歌词视频] 背景图下载失败，回退纯色背景，原因: {str(e)}")
            bg_image_dir = None
            bg_image_paths = []
            bg_image_concat_file = None
            use_bg_image = False

    try:
        # fontsdir：优先使用字体文件所在目录；若字体不在磁盘（如 volume 未挂载），回退系统字体目录
        font_file = Path(font_path)
        if font_file.exists():
            fontsdir = str(font_file.parent)
        else:
            _sys_font_dir = "/usr/share/fonts/truetype/noto"
            fontsdir = _sys_font_dir if Path(_sys_font_dir).exists() else str(font_file.parent)

        escaped_ass = ass_file.replace('\\', '/').replace(':', '\\:')
        escaped_fontsdir = fontsdir.replace('\\', '/').replace(':', '\\:')

        if use_bg_video:
            vf = _build_dimmed_cover_filter(width, height, escaped_ass, escaped_fontsdir)

            args = [
                "-ss", f"{bg_seek_start:.3f}",
                "-i", str(bg_video_path),
                "-i", audio_path,
                "-t", str(audio_duration),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "1",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v", "-map", "1:a",
            ]
        elif use_bg_image and bg_image_concat_file:
            vf = _build_dimmed_cover_filter(width, height, escaped_ass, escaped_fontsdir)

            args = [
                "-f", "concat",
                "-safe", "0",
                "-i", bg_image_concat_file,
                "-i", audio_path,
                "-t", str(audio_duration),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "1",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v", "-map", "1:a",
                "-movflags", "+faststart",
            ]
        elif normalized_background_mode == "color":
            glow_bg = _build_glow_background_source(width, height, ffmpeg_bg_color)
            vf = _build_glow_background_filter(escaped_ass, escaped_fontsdir)

            args = [
                "-f", "lavfi",
                "-i", glow_bg,
                "-i", audio_path,
                "-t", str(audio_duration),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-threads", "2",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v", "-map", "1:a",
                "-movflags", "+faststart",
            ]
        else:
            glow_background = _build_glow_background_source(width, height, ffmpeg_bg_color)
            vf = _build_glow_background_filter(escaped_ass, escaped_fontsdir)

            args = [
                "-f", "lavfi",
                "-i", glow_background,
                "-i", audio_path,
                "-t", str(audio_duration),
                "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "1",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v", "-map", "1:a",
                "-movflags", "+faststart",
            ]

        result_path = await execute_ffmpeg(audio_path, args, ".mp4", timeout=300)
        logger.info(f"[歌词视频] 合成完成: {result_path}")
        return result_path

    finally:
        if os.path.exists(ass_file):
            os.remove(ass_file)
        if bg_image_concat_file and os.path.exists(bg_image_concat_file):
            os.remove(bg_image_concat_file)
        if bg_image_dir and os.path.exists(bg_image_dir):
            shutil.rmtree(bg_image_dir, ignore_errors=True)


async def merge_audio(input_paths: list[str]) -> str:
    """
    音乐合并：支持调整顺序的合并
    使用 ffmpeg concat 滤镜
    """
    if not input_paths:
        raise ValueError("输入路径列表不能为空")
        
    if len(input_paths) == 1:
        # 单个文件直接返回副本
        temp_dest = tempfile.mktemp(suffix=Path(input_paths[0]).suffix)
        shutil.copy2(input_paths[0], temp_dest)
        return temp_dest

    # 构建 ffmpeg 参数
    args = []
    for p in input_paths:
        args.extend(["-i", p])
    
    # concat 滤镜: [0:a][1:a]...concat=n=N:v=0:a=1[outa]
    filter_complex = "".join([f"[{i}:a]" for i in range(len(input_paths))])
    filter_complex += f"concat=n={len(input_paths)}:v=0:a=1[outa]"
    
    args.extend([
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-c:a", "libmp3lame", # 统一输出为 MP3
        "-q:a", "2"
    ])
    
    return await execute_ffmpeg("merge_audio", args, ".mp3")
