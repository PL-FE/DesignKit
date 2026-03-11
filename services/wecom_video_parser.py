import re
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# 请求头，模拟浏览器访问，规避反爬
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://channels.weixin.qq.com/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def is_valid_video_url(url: str) -> bool:
    """判断是否是视频号链接"""
    keywords = [
        "channels.weixin.qq.com",
        "weixin.qq.com/sph",
        "wx.video.qq.com",
    ]
    return any(kw in url for kw in keywords)


def parse_video_url(share_url: str) -> dict:
    """
    解析视频号分享链接，提取无水印视频直链。

    返回格式：
        {"success": True, "video_url": "...", "title": "..."}
        {"success": False, "error": "错误信息"}
    """
    if not is_valid_video_url(share_url):
        return {"success": False, "error": "链接不是视频号分享链接，请检查后重试"}

    try:
        logger.info(f"开始解析视频号链接: {share_url}")
        response = requests.get(
            share_url,
            headers=HEADERS,
            timeout=15,
            allow_redirects=True,
        )
        response.raise_for_status()
        html = response.text

        # 方式1：从 script 标签中直接提取 video_url 字段（JSON 数据中）
        video_url = _extract_from_script(html)

        # 方式2：从 og:video meta 标签提取（备用）
        if not video_url:
            video_url = _extract_from_meta(html)

        if not video_url:
            return {"success": False, "error": "解析失败：未能从页面中提取视频地址，可能需要登录或页面结构已变更"}

        title = _extract_title(html) or "视频号视频"
        logger.info(f"解析成功: {title}")
        return {"success": True, "video_url": video_url, "title": title}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "请求超时，请稍后重试"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"网络请求失败：{str(e)}"}
    except Exception as e:
        logger.exception("视频解析异常")
        return {"success": False, "error": f"解析出现未知错误：{str(e)}"}


def _extract_from_script(html: str) -> str | None:
    """从 <script> 标签的 JSON 数据中提取 video_url"""
    patterns = [
        r'"url"\s*:\s*"(https://[^"]+\.mp4[^"]*)"',
        r'"video_url"\s*:\s*"(https://[^"]*\.mp4[^"]*)"',
        r'"videoUrl"\s*:\s*"(https://[^"]*\.mp4[^"]*)"',
        r'video_url\\?":\\?"(https://[^"\\]*.mp4[^"\\]*)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            url = match.group(1).encode().decode("unicode_escape")
            url = url.replace("\\/", "/")
            return url
    return None


def _extract_from_meta(html: str) -> str | None:
    """从 og:video meta 标签提取"""
    soup = BeautifulSoup(html, "lxml")
    meta = soup.find("meta", property="og:video")
    if meta and meta.get("content"):
        return meta["content"]
    return None


def _extract_title(html: str) -> str | None:
    """提取视频标题"""
    soup = BeautifulSoup(html, "lxml")
    meta = soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        return meta["content"]
    if soup.title:
        return soup.title.string
    return None
