import urllib.parse
import urllib.request
import json
import zlib
import base64
import logging
import uuid
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# KRC 歌词解密密钥
KRC_XOR_KEY = [64, 71, 97, 119, 94, 50, 116, 71, 81, 54, 49, 45, 206, 210, 110, 105]

def decrypt_krc(krc_bytes: bytes) -> str:
    """
    解密酷狗 KRC 加密歌词
    """
    if not krc_bytes.startswith(b"krc1"):
        return krc_bytes.decode("utf-8", errors="ignore")
    
    # 移除前4字节的 "krc1" 头部
    data = bytearray(krc_bytes[4:])
    
    # 异或解密
    for i in range(len(data)):
        data[i] = data[i] ^ KRC_XOR_KEY[i % 16]
        
    try:
        # zlib 解压缩
        decompressed = zlib.decompress(data)
        return decompressed.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.error(f"KRC zlib 解压失败: {e}")
        return ""

import re

def parse_time_to_seconds(time_str: str) -> float:
    parts = time_str.split(':')
    if len(parts) < 2:
        return 0.0
    try:
        mins = float(parts[0])
        secs = float(parts[1])
        return mins * 60 + secs
    except ValueError:
        return 0.0

def format_seconds_to_time(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:06.3f}"

def krc_to_lrc(krc_text: str) -> str:
    """
    将酷狗 KRC (相对偏移字轴歌词) 转换为 Enhanced LRC (绝对时间戳字轴歌词)
    兼容:
    1. [34389,6481]<0,393,0>远<393,472,0>方... (纯毫秒数格式)
    2. [00:15.516<2000>]我<0,300,0>怕... (分秒格式)
    """
    lines = krc_text.split('\n')
    lrc_lines = []
    
    # 模式1: 纯毫秒数格式, 如 [34389,6481]
    ms_line_pattern = re.compile(r'^\[(\d+),(\d+)\](.*)')
    
    # 模式2: 分秒格式, 如 [00:15.516<2000>] 或 [00:15.51<2000>]
    time_line_pattern = re.compile(r'^\[(\d{2,}:\d{2}(?:\.\d{1,3})?)<(\d+)>\](.*)')
    
    word_pattern = re.compile(r'<(\d+),(\d+),\d+>([^<]*)')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # 1. 尝试匹配模式1 (纯毫秒格式)
        ms_match = ms_line_pattern.match(line)
        if ms_match:
            start_ms = int(ms_match.group(1))
            line_duration_ms = int(ms_match.group(2))
            content = ms_match.group(3)
            
            line_start_sec = start_ms / 1000.0
            formatted_line_time = format_seconds_to_time(line_start_sec)
            
            words = word_pattern.findall(content)
            if not words:
                lrc_lines.append(f"[{formatted_line_time}]{content}")
                continue
                
            new_line_parts = [f"[{formatted_line_time}]"]
            for offset_str, duration_str, word_text in words:
                offset_ms = int(offset_str)
                word_start_sec = (start_ms + offset_ms) / 1000.0
                formatted_word_time = format_seconds_to_time(word_start_sec)
                new_line_parts.append(f"<{formatted_word_time}>{word_text}")
                
            # 闭合最后一个标签
            line_end_sec = (start_ms + line_duration_ms) / 1000.0
            formatted_end_time = format_seconds_to_time(line_end_sec)
            new_line_parts.append(f"<{formatted_end_time}>")
            
            lrc_lines.append("".join(new_line_parts))
            continue
            
        # 2. 尝试匹配模式2 (分秒格式)
        time_match = time_line_pattern.match(line)
        if time_match:
            time_str = time_match.group(1)
            line_duration_ms = int(time_match.group(2))
            content = time_match.group(3)
            
            line_start_sec = parse_time_to_seconds(time_str)
            formatted_line_time = time_str
            
            words = word_pattern.findall(content)
            if not words:
                lrc_lines.append(f"[{formatted_line_time}]{content}")
                continue
                
            new_line_parts = [f"[{formatted_line_time}]"]
            for offset_str, duration_str, word_text in words:
                offset_ms = int(offset_str)
                word_start_sec = line_start_sec + (offset_ms / 1000.0)
                formatted_word_time = format_seconds_to_time(word_start_sec)
                new_line_parts.append(f"<{formatted_word_time}>{word_text}")
                
            line_end_sec = line_start_sec + (line_duration_ms / 1000.0)
            formatted_end_time = format_seconds_to_time(line_end_sec)
            new_line_parts.append(f"<{formatted_end_time}>")
            
            lrc_lines.append("".join(new_line_parts))
            continue
            
        # 3. 其它行直接保留
        lrc_lines.append(line)
        
    return "\n".join(lrc_lines)

def http_get_json(url: str, headers: dict = None) -> dict:
    """
    封装极简 of HTTP GET 请求，并解析为 JSON
    """
    if headers is None:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.error(f"请求失败 {url}: {e}")
        return {}

@router.get("/music/search")
def search_music(
    keyword: str = Query(..., description="搜索关键词"),
    page: int = Query(1, description="页码"),
    pagesize: int = Query(15, description="每页歌曲数量")
):
    """
    酷狗音乐歌曲搜索接口
    """
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"http://songsearch.kugou.com/song_search_v2?keyword={encoded_keyword}&page={page}&pagesize={pagesize}&platform=WebFilter"
    
    res = http_get_json(url)
    if not res or res.get("status") != 1:
        return JSONResponse({"code": 500, "message": "酷狗搜索接口调用失败", "data": []})
        
    lists = res.get("data", {}).get("lists", [])
    songs = []
    for item in lists:
        songs.append({
            "song_name": item.get("SongName", ""),
            "singer_name": item.get("SingerName", ""),
            "hash": item.get("FileHash", ""),
            "album_id": item.get("AlbumID", ""),
            "duration": item.get("Duration", 0)  # 单位：秒
        })
        
    return {"code": 200, "message": "success", "data": songs}

@router.get("/music/lrc")
def get_music_lrc(
    hash: str = Query(..., description="酷狗歌曲 Hash"),
    song_name: str = Query("", description="歌名，用于备用搜索"),
    artist_name: str = Query("", description="歌手名，用于备用搜索")
):
    """
    获取歌词（优先获取酷狗精准字轴 KRC 歌词，解密转换；失败后尝试 lrclib）
    """
    # 1. 尝试酷狗歌词搜索
    # 优先基于 hash 精准匹配歌词
    encoded_song = urllib.parse.quote(song_name)
    url = f"http://lyrics.kugou.com/search?ver=1&man=yes&client=pc&keyword={encoded_song}&hash={hash}"
    
    res = http_get_json(url)
    candidates = res.get("candidates", [])
    
    # 如果基于 hash 没搜到，尝试只按歌名搜索
    if not candidates and song_name:
        url_by_name = f"http://lyrics.kugou.com/search?ver=1&man=yes&client=pc&keyword={encoded_song}"
        res = http_get_json(url_by_name)
        candidates = res.get("candidates", [])
        
    # 如果搜到了酷狗歌词候选
    if candidates:
        # 取第一个最匹配的
        best = candidates[0]
        lrc_id = best.get("id")
        accesskey = best.get("accesskey")
        
        # 下载加密歌词
        download_url = f"http://lyrics.kugou.com/download?ver=1&client=pc&id={lrc_id}&accesskey={accesskey}&fmt=krc"
        dl_res = http_get_json(download_url)
        
        content_b64 = dl_res.get("content", "")
        if content_b64:
            try:
                # Base64 解码得到加密字节流
                encrypted_bytes = base64.b64decode(content_b64)
                # 解密 KRC
                decrypted_lrc = decrypt_krc(encrypted_bytes)
                if decrypted_lrc:
                    converted_lrc = krc_to_lrc(decrypted_lrc)
                    return {"code": 200, "message": "success", "source": "kugou", "lyric": converted_lrc}
            except Exception as e:
                logger.error(f"解析酷狗 KRC 失败: {e}")

    # 2. 备用方案：通过 lrclib 获取同步歌词
    if song_name:
        try:
            q = f"{song_name} {artist_name}".strip()
            encoded_q = urllib.parse.quote(q)
            lrclib_url = f"https://lrclib.net/api/search?q={encoded_q}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Lrclib-Client": "DesignKitLyricVideoApp"
            }
            req = urllib.request.Request(lrclib_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                search_res = json.loads(response.read().decode("utf-8"))
                if search_res and isinstance(search_res, list):
                    # 优先取带 syncedLyrics 的歌词
                    for s_item in search_res:
                        synced = s_item.get("syncedLyrics")
                        if synced:
                            return {"code": 200, "message": "success", "source": "lrclib", "lyric": synced}
                    # 其次取 plainLyrics
                    for s_item in search_res:
                        plain = s_item.get("plainLyrics")
                        if plain:
                            return {"code": 200, "message": "success", "source": "lrclib_plain", "lyric": plain}
        except Exception as e:
            logger.error(f"lrclib 获取歌词失败: {e}")
            
    return JSONResponse(status_code=200, content={"code": 404, "message": "未能获取到匹配的歌词", "lyric": ""})

@router.get("/music/audio-proxy")
def audio_proxy(
    hash: str = Query(..., description="酷狗歌曲 Hash"),
    album_id: str = Query("", description="酷狗 AlbumID")
):
    """
    音频跨域下载/播放代理（流式传输并添加 CORS 支持）
    """
    # 1. 尝试酷狗移动端接口获取播放地址
    url = f"http://m.kugou.com/app/i/getSongInfo.php?cmd=playInfo&hash={hash}"
    info = http_get_json(url)
    
    play_url = info.get("url")
    
    # 2. 备用方案：通过 play/getdata 接口获取播放地址
    if not play_url:
        kg_mid = str(uuid.uuid4()).replace("-", "")
        getdata_url = f"https://wwwapi.kugou.com/yy/index.php?r=play/getdata&hash={hash}&album_id={album_id}&mid=1&platid=4"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.kugou.com/song/",
            "Cookie": f"kg_mid={kg_mid}; kg_dfid=1; kg_dfid_collect=d41d8cd98f00b204e9800998ecf8427e"
        }
        res_data = http_get_json(getdata_url, headers=headers)
        play_url = res_data.get("data", {}).get("play_url", "")

    if not play_url:
        raise HTTPException(status_code=404, detail="未能获取到该歌曲的有效音频地址")

    # 3. 代理请求并将音频以流的形式返回给前端（添加 CORS Header）
    def generate_audio_stream():
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.kugou.com/"
        }
        try:
            req = urllib.request.Request(play_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as conn:
                while True:
                    chunk = conn.read(65536)  # 64KB
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            logger.error(f"代理音频数据流传输异常: {e}")

    # 返回流式响应，同时带上 CORS 头以允许前端 Web Audio API 解码
    return StreamingResponse(
        generate_audio_stream(),
        media_type="audio/mpeg",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Content-Disposition": f"inline; filename={hash}.mp3"
        }
    )
