import os
import re
import aiohttp
import aiofiles
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def format_time(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "مباشر 🔴"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def clean_title(title: str) -> str:
    title = re.sub(r'\(.*?\)|\[.*?\]', '', title)
    title = re.sub(r'(Official|Music|Video|Lyrics|HD|HQ|Audio|MV)', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s+', ' ', title).strip()
    return title[:60] if len(title) > 60 else title

async def get_thumb(url: str) -> str | None:
    if not url:
        return None
    try:
        thumb_dir = Path("thumbs")
        thumb_dir.mkdir(exist_ok=True)
        
        filename = thumb_dir / f"{hash(url)}.jpg"
        if filename.exists():
            return str(filename)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    async with aiofiles.open(filename, 'wb') as f:
                        await f.write(content)
                    return str(filename)
    except Exception as e:
        logger.warning(f"Thumb error: {e}")
    return None

def progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "░" * length
    filled = int(length * current / total)
    bar = "█" * filled + "░" * (length - filled)
    percent = int(100 * current / total)
    return f"{bar} {percent}%"

def format_number(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)
