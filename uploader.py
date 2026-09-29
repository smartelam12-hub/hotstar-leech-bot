"""
uploader.py – Upload a local file to Telegram with live progress updates.

Supports:
  - Video upload (send_video) for .mp4 / .mkv / etc.
  - Document upload (send_document) for everything else
  - Optional mirroring to DUMP_CHAT_ID
  - Live rich progress card edited into status message
"""
import time
from pathlib import Path
from typing import Optional

from pyrogram import Client
from pyrogram.types import Message

import config
from utils import format_progress_card, RateLimiter


async def upload_file(
    client: Client,
    chat_id: int,
    file_path: Path,
    caption: str,
    status_msg: Optional[Message] = None,
    reply_to: Optional[int] = None,
    user_name: str = "User",
    user_id: int = 0,
    quality: str = "Best",
    audio: str = "Default",
) -> Message:
    """
    Upload *file_path* to *chat_id* with live rich progress card.
    """
    limiter = RateLimiter(interval=5.0)


    start_time = time.monotonic()
    title = file_path.name

    async def _progress(current: int, total: int):
        if not limiter.should_call():
            return
        if status_msg is None:
            return
        elapsed = max(time.monotonic() - start_time, 0.1)
        speed = current / elapsed
        text = format_progress_card(
            title=title,
            user_name=user_name,
            user_id=user_id,
            current_bytes=current,
            total_bytes=total,
            speed_bytes_sec=speed,
            status_label="Uploading to Telegram",
            quality=quality,
            audio=audio,
        )
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass

    ext = file_path.suffix.lower()
    send_kwargs = dict(
        chat_id=chat_id,
        caption=caption,
        progress=_progress,
        reply_to_message_id=reply_to,
    )

    if ext in (".mp4", ".mkv", ".webm", ".avi", ".mov"):
        sent = await client.send_video(
            video=str(file_path),
            supports_streaming=True,
            **send_kwargs,
        )
    else:
        sent = await client.send_document(
            document=str(file_path),
            **send_kwargs,
        )

    # ── Mirror to dump chat if configured ────────────────────────────────────
    if config.DUMP_CHAT_ID and config.DUMP_CHAT_ID != chat_id:
        try:
            await sent.copy(config.DUMP_CHAT_ID)
        except Exception:
            pass

    return sent
