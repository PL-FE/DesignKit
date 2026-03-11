import os
import time
import logging
import httpx

logger = logging.getLogger(__name__)

WECOM_CORP_ID: str = os.getenv("WECOM_CORP_ID", "")
WECOM_AGENT_ID: str = os.getenv("WECOM_AGENT_ID", "")
WECOM_SECRET: str = os.getenv("WECOM_SECRET", "")

WECOM_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"

# access_token 简单内存缓存
_token_cache: dict = {"token": None, "expires_at": 0}


async def _get_access_token() -> str:
    """获取企微 access_token（带内存缓存，有效期 7200 秒）"""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]

    url = f"{WECOM_API_BASE}/gettoken"
    params = {"corpid": WECOM_CORP_ID, "corpsecret": WECOM_SECRET}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        data = resp.json()

    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"获取 access_token 失败: {data}")

    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data.get("expires_in", 7200) - 60
    logger.info("企微 access_token 已刷新")
    return _token_cache["token"]


async def send_text_message(user_id: str, content: str) -> bool:
    """主动发送文本消息给指定企微用户"""
    try:
        token = await _get_access_token()
        url = f"{WECOM_API_BASE}/message/send?access_token={token}"
        payload = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": int(WECOM_AGENT_ID),
            "text": {"content": content},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10)
            data = resp.json()

        if data.get("errcode", 0) != 0:
            logger.error(f"发送消息失败: {data}")
            return False

        logger.info(f"成功发送消息给用户 {user_id}")
        return True
    except Exception as e:
        logger.exception(f"发送消息异常: {e}")
        return False
