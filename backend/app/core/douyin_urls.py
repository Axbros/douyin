import re
from urllib.parse import urlparse


DOUYIN_URL_PATTERN = re.compile(r"https?://(?:v\.douyin\.com|live\.douyin\.com)/[^\s<>\"'\]\)]+", re.IGNORECASE)
ALLOWED_DOUYIN_HOSTS = {"v.douyin.com", "live.douyin.com"}
TRAILING_SHARE_PUNCTUATION = "，。！？、；：,.!?;:)]}》】"


def extract_douyin_live_url(share_text: str) -> str:
    """从抖音分享文案或纯链接中提取允许访问的直播链接。"""
    match = DOUYIN_URL_PATTERN.search(share_text.strip())
    if not match:
        raise ValueError("未识别到抖音直播链接，请粘贴包含链接的完整分享内容")
    url = match.group(0).rstrip(TRAILING_SHARE_PUNCTUATION)
    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_DOUYIN_HOSTS:
        raise ValueError("只支持抖音直播分享链接")
    return url
