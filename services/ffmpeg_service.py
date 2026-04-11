import asyncio
import tempfile
import shutil
import logging
import os
from pathlib import Path
import json

logger = logging.getLogger(__name__)

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

async def execute_ffmpeg(input_path: str, args: list[str], output_ext: str) -> str:
    """
    异步调用 ffmpeg 外部命令行工具
    
    :param input_path: 输入文件路径 (为了记录或日志)
    :param args: ffmpeg 后面的命令参数 (不包含"ffmpeg")，注意需要包含 -y 覆盖以及输出路径
    :param output_ext: 输出文件后缀，例如 ".mp4"
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
        
        _, stderr = await process.communicate()
        
        if process.returncode != 0:
            err_msg = stderr.decode()
            logger.error(f"ffmpeg 执行失败: {err_msg}")
            raise RuntimeError("媒体处理失败，可能是不支持的格式或参数配置错误")
            
        if not output_file.exists():
            raise RuntimeError("FFmpeg 执行成功，但并未生成输出文件")
            
        # 复制到独立路径后立刻清理目录
        temp_dest = tempfile.mktemp(suffix=output_ext)
        shutil.copy2(output_file, temp_dest)
        return temp_dest
        
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)

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
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env
        )
        
        stdout, stderr = await process.communicate()
        
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
    支持标准格式：[mm:ss.xx] 歌词文字
    返回: [{"time": float（秒）, "text": str}]
    """
    import re
    lines = []
    # 匹配标准 LRC 时间标签
    time_pattern = re.compile(r'\[(\d{1,3}):(\d{2})\.(\d{1,3})\](.*)$')

    for raw_line in lrc_content.splitlines():
        raw_line = raw_line.strip()
        # 同一行可能有多个时间标签（如 [00:01.00][00:30.00]歌词）
        tags = re.findall(r'\[(\d{1,3}):(\d{2})\.(\d{1,3})\]', raw_line)
        if not tags:
            continue
        # 提取歌词文本（最后一个时间标签后面的所有内容）
        text = re.sub(r'\[\d{1,3}:\d{2}\.\d{1,3}\]', '', raw_line).strip()
        if not text:
            continue
        for m, s, cs in tags:
            minutes = int(m)
            seconds = int(s)
            centiseconds_str = cs.ljust(3, '0')[:3]  # 统一为3位毫秒
            milliseconds = int(centiseconds_str)
            total_seconds = minutes * 60 + seconds + milliseconds / 1000.0
            lines.append({"time": total_seconds, "text": text})

    # 按时间排序
    lines.sort(key=lambda x: x["time"])
    return lines


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
    font_color: str,
    stroke_color: str,
    stroke_width: int,
    resolution: str,
    letter_spacing: int = 2,
    line_gap_ratio: float = 1.8,
) -> str:
    """
    将解析后的 LRC 行列表转换为 ASS 字幕格式字符串。
    三行滚动模式（带动画）：
      - 上方行：淡色小字（前一句），淡入
      - 中间行：正常颜色大字（当前句，居中），从下方滚入 + 淡入
      - 下方行：淡色小字（后一句），淡入
    font_color / stroke_color 格式为 "#rrggbb"
    letter_spacing: 字符间额外间距（px），对应 ASS Spacing 字段
    line_gap_ratio: 行间距倍数（相对于 font_size），默认 1.8
    """
    def hex_to_ass_color(hex_color: str, alpha: str = "00") -> str:
        """#RRGGBB → ASS &HAABBGGRR (AA=00 不透明, FF 完全透明)"""
        h = hex_color.lstrip('#')
        r, g, b = h[0:2], h[2:4], h[4:6]
        return f"&H{alpha}{b}{g}{r}"

    width, height = map(int, resolution.lower().split('x'))
    cx = width // 2   # 水平居中 X
    cy = height // 2  # 垂直居中 Y

    # 正常颜色（当前行）
    primary_color = hex_to_ass_color(font_color, "00")
    outline_color = hex_to_ass_color(stroke_color, "00")

    # 淡色（上下行），透明度约 52%（0x85）
    dim_color = hex_to_ass_color(font_color, "85")
    dim_outline = hex_to_ass_color(stroke_color, "85")

    # 上下行字号为当前行的 68%，描边相应缩小
    dim_size = max(36, int(font_size * 0.68))
    dim_stroke = max(1, stroke_width - 1)
    dim_spacing = max(0, letter_spacing - 1)

    # 行间距（中间行中心 → 旁边行中心）
    line_gap = int(font_size * line_gap_ratio)

    # 动画参数（单位：毫秒），只用淡入淡出，不移动
    anim_in_ms = 300    # 当前行淡入时长
    fade_out_ms = 150   # 结束前淡出时长
    dim_fade_ms = 250   # 上下行淡入时长

    # ASS 文件头，定义两种 Style
    # Spacing 字段控制字符间距；Alignment=5 垂直水平居中
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,{letter_spacing},0,1,{stroke_width},2,5,0,0,0,1
Style: Dim,{font_name},{dim_size},{dim_color},&H000000FF,{dim_outline},&H80000000,0,0,0,0,100,100,{dim_spacing},0,1,{dim_stroke},2,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("{", "\\{")

    events = []
    for i, line in enumerate(lrc_lines):
        start = line["time"]
        # 结束时间为下一句开始前 0.05 秒，或音频总时长
        if i + 1 < len(lrc_lines):
            end = lrc_lines[i + 1]["time"] - 0.05
        else:
            end = audio_duration
        # 最小显示 0.5 秒
        if end <= start:
            end = start + 0.5

        s = _seconds_to_ass_time(start)
        e = _seconds_to_ass_time(end)

        curr_text = escape(line["text"])

        # 当前行（中间，正常颜色，Layer=1）
        # 纯淡入淡出旲动，无移动动画
        curr_tag = (
            f"{{\\an5"
            f"\\pos({cx},{cy})"
            f"\\fad({anim_in_ms},{fade_out_ms})"
            f"}}"
        )
        events.append(
            f"Dialogue: 1,{s},{e},Default,,0,0,0,,{curr_tag}{curr_text}"
        )

        # 上一行（当前行上方，淡色，Layer=0）
        # 静止在上方位置，淡入显示（无需移动，是已显示的前一句）
        if i > 0:
            prev_text = escape(lrc_lines[i - 1]["text"])
            prev_y = cy - line_gap
            dim_tag = (
                f"{{\\an5"
                f"\\pos({cx},{prev_y})"
                f"\\fad({dim_fade_ms},0)"
                f"}}"
            )
            events.append(
                f"Dialogue: 0,{s},{e},Dim,,0,0,0,,{dim_tag}{prev_text}"
            )

        # 下一行（当前行下方，淡色，Layer=0）
        # 静止在下方位置，淡入显示
        if i + 1 < len(lrc_lines):
            next_text = escape(lrc_lines[i + 1]["text"])
            next_y = cy + line_gap
            dim_tag = (
                f"{{\\an5"
                f"\\pos({cx},{next_y})"
                f"\\fad({dim_fade_ms},0)"
                f"}}"
            )
            events.append(
                f"Dialogue: 0,{s},{e},Dim,,0,0,0,,{dim_tag}{next_text}"
            )

    return header + "\n".join(events) + "\n"




async def generate_lyric_video(
    audio_path: str,
    lrc_lines: list[dict],
    bg_color: str,
    font_size: int,
    font_color: str,
    stroke_color: str,
    stroke_width: int,
    resolution: str,
    font_path: str,
    letter_spacing: int = 2,
    line_gap_ratio: float = 1.8,
) -> str:
    """
    使用 FFmpeg 将音频和解析后的 LRC 歌词合成为带字幕的 MP4 视频。

    流程：
    1. 通过 ffprobe 获取音频时长
    2. 将 lrc_lines 转换为 ASS 字幕文件（临时文件）
    3. FFmpeg 生成纯色背景 + 叠加字幕 + 合并音频

    返回临时输出 mp4 文件路径
    """
    logger.info(f"[歌词视频] 开始合成，音频: {audio_path}, 歌词行数: {len(lrc_lines)}, 分辨率: {resolution}")

    # 1. 获取音频时长
    probe_data = await execute_ffprobe(audio_path)
    audio_duration = float(probe_data.get("format", {}).get("duration", 0))
    if audio_duration <= 0:
        raise RuntimeError("无法读取音频时长，请检查文件格式")
    logger.info(f"[歌词视频] 音频时长: {audio_duration:.2f}s")

    # 2. 提取字体名（FFmpeg ASS 滤镜需要字体名而非路径）
    # 对于内嵌字体或已安装字体，只需提供 font name；
    # 若直接指定字体文件路径，需要用 fontsdir 或 force_style
    font_name = Path(font_path).stem  # e.g. "NotoSansSC-Bold"

    # 3. 生成 ASS 字幕内容
    ass_content = _lrc_to_ass(
        lrc_lines=lrc_lines,
        audio_duration=audio_duration,
        font_name=font_name,
        font_size=font_size,
        font_color=font_color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        resolution=resolution,
        letter_spacing=letter_spacing,
        line_gap_ratio=line_gap_ratio,
    )

    # 4. 写入临时 ASS 文件
    ass_file = tempfile.mktemp(suffix=".ass")
    with open(ass_file, 'w', encoding='utf-8') as f:
        f.write(ass_content)
    logger.info(f"[歌词视频] 已生成 ASS 字幕: {ass_file}")

    # 5. 解析分辨率
    width, height = resolution.lower().split('x')

    # 6. 处理背景颜色（#RRGGBB → FFmpeg color=0xRRGGBB）
    bg_hex = bg_color.lstrip('#')
    ffmpeg_bg_color = f"0x{bg_hex}"

    try:
        # 7. 构建 FFmpeg 命令
        # 视频流：lavfi color 生成纯色背景，叠加 ASS 字幕
        # 音频流：直接使用输入音频
        # ASS 字幕中指定 fontsdir 以便 FFmpeg 找到自定义字体
        fontsdir = str(Path(font_path).parent)

        # ASS 路径在 Windows 需要转义冒号，Linux/Mac 直接用即可
        escaped_ass = ass_file.replace('\\', '/').replace(':', '\\:')
        escaped_fontsdir = fontsdir.replace('\\', '/').replace(':', '\\:')

        vf = (
            f"subtitles='{escaped_ass}':fontsdir='{escaped_fontsdir}'"
        )

        args = [
            # 视频流：纯色背景
            "-f", "lavfi",
            "-i", f"color=c={ffmpeg_bg_color}:size={width}x{height}:rate=25",
            # 音频流
            "-i", audio_path,
            # 时长与音频一致
            "-t", str(audio_duration),
            # 视频滤镜：叠加 ASS 字幕
            "-vf", vf,
            # 编码
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            # 映射：第一个输入的视频 + 第二个输入的音频
            "-map", "0:v", "-map", "1:a",
        ]

        result_path = await execute_ffmpeg(audio_path, args, ".mp4")
        logger.info(f"[歌词视频] 合成完成: {result_path}")
        return result_path

    finally:
        # 清理临时 ASS 文件
        if os.path.exists(ass_file):
            os.remove(ass_file)


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
