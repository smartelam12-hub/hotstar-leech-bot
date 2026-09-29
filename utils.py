"""
utils.py – Shared helper utilities for V2.
"""
import os
import re
import time
from typing import Optional
import psutil
import yt_dlp

# ── URL patterns ──────────────────────────────────────────────────────────────

_HOTSTAR_PATTERN = re.compile(
    r"https?://(www\.)?(hotstar\.com|jiohotstar\.com|disneyplus\.hotstar\.com|hss\.hotstar\.com)"
    r"(/[^\s]+)",
    re.IGNORECASE,
)

_MXPLAYER_PATTERN = re.compile(
    r"https?://(www\.)?(mxplayer\.in|mxplayer\.com)"
    r"(/[^\s]+)",
    re.IGNORECASE,
)


def is_supported_url(url: str) -> bool:
    """Return True if url matches any supported platform."""
    url = url.strip()
    return bool(_HOTSTAR_PATTERN.match(url) or _MXPLAYER_PATTERN.match(url))


def extract_url(text: str) -> Optional[str]:
    """Extract first supported URL from text, or None."""
    for pattern in (_HOTSTAR_PATTERN, _MXPLAYER_PATTERN):
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


# ── Human-readable formatting ──────────────────────────────────────────────────

def human_size(num_bytes: int | float) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f}{unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f}TB"


def human_duration(seconds: int) -> str:
    """Convert seconds to HH:MM:SS or MM:SS string."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def circle_progress_bar(current: int, total: int, width: int = 12) -> str:
    """Return circle progress bar like [●●◐ooooooooo]."""
    if total <= 0:
        return "o" * width
    pct = min(1.0, max(0.0, current / total))
    filled_units = pct * width
    full = int(filled_units)
    half = 1 if (filled_units - full) >= 0.5 else 0
    empty = max(0, width - full - half)
    return "●" * full + ("◐" if half else "") + "o" * empty


def progress_bar(current: int, total: int, width: int = 12) -> str:
    """Return standard ASCII progress bar."""
    return circle_progress_bar(current, total, width)


# ── System Stats & Rich Progress Card ──────────────────────────────────────────

_BOOT_TIME = psutil.boot_time()

def get_system_stats():
    """Fetch current CPU, RAM, disk, and uptime stats."""
    cpu_pct = psutil.cpu_percent(interval=None)
    ram_pct = psutil.virtual_memory().percent
    free_disk = human_size(psutil.disk_usage(".").free)
    uptime_secs = int(time.time() - _BOOT_TIME)
    d, rem = divmod(uptime_secs, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    uptime_str = f"{d}d{h}h{m}m" if d else f"{h}h{m}m"
    return cpu_pct, ram_pct, free_disk, uptime_str


_YTDLP_VER = getattr(yt_dlp, "__version__", "v2026.9.27")


def format_progress_card(
    title: str,
    user_name: str,
    user_id: int,
    current_bytes: int,
    total_bytes: int,
    speed_bytes_sec: float,
    status_label: str = "Download",
    quality: str = "Best",
    audio: str = "Default",
) -> str:
    """
    Format a rich tree-style progress card matching the user's design.
    """
    pct = (current_bytes / total_bytes * 100.0) if total_bytes > 0 else 0.0
    bar = circle_progress_bar(current_bytes, total_bytes, width=12)
    done_str = human_size(current_bytes)
    total_str = human_size(total_bytes) if total_bytes > 0 else "Unknown"
    speed_str = f"{human_size(speed_bytes_sec)}/s" if speed_bytes_sec > 0 else "0.0B/s"
    
    if speed_bytes_sec > 0 and total_bytes > current_bytes:
        eta_sec = int((total_bytes - current_bytes) / speed_bytes_sec)
        m, s = divmod(eta_sec, 60)
        h, m = divmod(m, 60)
        eta_str = f"{h}h{m}m" if h else (f"{m}m{s}s" if m else f"{s}s")
    else:
        eta_str = "0s"

    cpu_pct, ram_pct, free_disk, uptime_str = get_system_stats()

    return (
        f"🎬 **{title}**\n\n"
        f"╭ 👤 **{user_name}** (`#ID{user_id}`)\n"
        f"├ [{bar}]\n"
        f"├ **Progress** : `{pct:.2f}%`\n"
        f"├ **Done** : `{done_str}`\n"
        f"├ **Total** : `{total_str}`\n"
        f"├ **Speed** : `{speed_str}`\n"
        f"├ **ETA** : `{eta_str}`\n"
        f"├ **Status** : `{status_label}`\n"
        f"├ **Engine** : `yt-dlp v{_YTDLP_VER.lstrip('v')}`\n"
        f"├ **Quality** : `{quality}` | **Audio** : `{audio}`\n"
        f"╰ **Cancel** : `/cancel` \n\n"
        f"╭ **System Stats**\n"
        f"├ **CPU** » `{cpu_pct}%` | **FREE** » `{free_disk}`\n"
        f"├ **RAM** » `{ram_pct}%` | **UP** » `{uptime_str}`\n"
        f"╰ **DL Speed** » `{speed_str}`"
    )


class RateLimiter:
    """Ensure a callable is invoked at most once per *interval* seconds."""

    def __init__(self, interval: float = 2.5):
        self.interval = interval
        self._last: float = 0.0

    def should_call(self) -> bool:
        now = time.monotonic()
        if now - self._last >= self.interval:
            self._last = now
            return True
        return False
