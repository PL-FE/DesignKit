import os
import asyncio
import logging
from fastapi import APIRouter, Request, Response, BackgroundTasks
from wechatpy.enterprise.crypto import WeChatCrypto
from wechatpy.enterprise import parse_message
from wechatpy.exceptions import InvalidSignatureException

from services.wecom_video_parser import parse_video_url, is_valid_video_url
from services.wecom_sender import send_text_message

router = APIRouter()
logger = logging.getLogger(__name__)

# 企微消息加解密实例（懒加载，避免配置未就绪时报错）
_crypto: WeChatCrypto | None = None


def get_crypto() -> WeChatCrypto:
    global _crypto
    if _crypto is None:
        token = os.getenv("WECOM_TOKEN", "")
        aes_key = os.getenv("WECOM_AES_KEY", "")
        corp_id = os.getenv("WECOM_CORP_ID", "")
        
        # 记录关键配置状态以便排查（不要打印明文密钥）
        if not token or not aes_key or not corp_id:
            logger.error(f"企业微信配置缺失！Token: {bool(token)}, AES_KEY: {bool(aes_key)}, CORP_ID: {bool(corp_id)}")
            raise ValueError("企业微信机器人环境变量配置不完整，请检查 WECOM_TOKEN/WECOM_AES_KEY/WECOM_CORP_ID")

        try:
            _crypto = WeChatCrypto(token.strip(), aes_key.strip(), corp_id.strip())
        except AssertionError as e:
            logger.error(f"企业微信 AES_KEY 配置格式不正确，期望 43 位字符，实际长度: {len(aes_key)}")
            raise ValueError(f"WECOM_AES_KEY 格式错误: {e}")
            
    return _crypto


@router.get("/wecom/callback")
async def verify_callback(
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str,
):
    """
    企业微信回调验证接口（GET）
    企微后台保存"接收消息服务器 URL"配置时，会请求此接口验证。
    """
    try:
        decrypted = get_crypto().check_signature(msg_signature, timestamp, nonce, echostr)
        logger.info("企微回调验证成功")
        return Response(content=decrypted, media_type="text/plain")
    except InvalidSignatureException:
        logger.warning("企微回调验证失败：签名不合法")
        return Response(content="非法请求", status_code=403)


@router.post("/wecom/callback")
async def receive_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str,
    timestamp: str,
    nonce: str,
):
    """
    企业微信消息接收接口（POST）
    接收用户消息并异步解析视频号链接，解析完成后主动回复（规避 5 秒超时限制）。
    """
    raw_body = await request.body()

    try:
        decrypted_xml = get_crypto().decrypt_message(raw_body, msg_signature, timestamp, nonce)
        msg = parse_message(decrypted_xml)
        logger.info(f"收到企微消息: type={msg.type}, from={msg.source}")
    except InvalidSignatureException:
        logger.warning("消息签名验证失败")
        return Response(content="", status_code=200)
    except Exception as e:
        logger.exception(f"消息解密/解析失败: {e}")
        return Response(content="", status_code=200)

    # 只处理文本消息
    if msg.type != "text":
        return Response(content="", status_code=200)

    user_id = msg.source
    content = msg.content.strip()

    if not is_valid_video_url(content):
        background_tasks.add_task(
            send_text_message,
            user_id,
            "👋 请发送视频号分享链接，我来帮你解析下载地址！\n\n支持的链接格式：\nhttps://channels.weixin.qq.com/...",
        )
    else:
        # 视频号链接：后台异步解析+回复，立即返回 200 避免企微重试
        background_tasks.add_task(_parse_and_reply, user_id, content)

    return Response(content="", status_code=200)


async def _parse_and_reply(user_id: str, url: str):
    """后台任务：解析视频号链接后主动发消息给用户"""
    await send_text_message(user_id, "⏳ 正在解析视频号链接，请稍候...")

    # 在线程池中执行同步请求，避免阻塞事件循环
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, parse_video_url, url)

    if result["success"]:
        video_url = result["video_url"]
        title = result.get("title", "视频")
        reply = (
            f"✅ 解析成功！\n\n"
            f"📹 标题：{title}\n\n"
            f"🔗 视频直链（复制到浏览器下载）：\n{video_url}"
        )
    else:
        reply = f"❌ 解析失败：{result['error']}\n\n请检查链接是否正确，或稍后重试。"

    await send_text_message(user_id, reply)
