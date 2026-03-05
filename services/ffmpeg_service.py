import asyncio
import tempfile
import shutil
import logging
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
    # 宽度最大限制为 600px，高度自动按比例缩放，并配合 fps 控制
    vf_str = f"fps={fps},scale=600:-1:flags=lanczos"
    
    if output_fmt == "gif":
        # GIF 为了质量好一点，一般采用 split+palettegen+paletteuse 复杂的滤镜组合
        # 简单高效起见，我们直接输出 GIF，并做 256 色优化处理
        vf_str += ",split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
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
