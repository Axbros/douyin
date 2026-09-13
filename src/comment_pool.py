"""导入和随机选取预设评论。"""
import random
from pathlib import Path


def parse_comments(text):
    return list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))


def read_comments(path):
    data = Path(path).read_bytes()
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return parse_comments(data.decode('utf-16'))
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('gb18030')
    if '\x00' in text:
        raise ValueError('文件不是支持的纯文本格式')
    return parse_comments(text)


def choose_comment(comments, recent, max_length):
    # 先按实际发送长度去重，避免不同长句截断后成为同一条评论。
    pool = list(dict.fromkeys(text.strip()[:max_length] for text in comments if text.strip()))
    if not pool:
        return ''
    window = min(len(pool) - 1, 15)
    excluded = set(recent[-window:]) if window else set()
    available = [text for text in pool if text not in excluded]
    return random.choice(available or pool)
