"""
bot.py – Telegram Leech Bot V2 (JioHotstar + MX Player)

Interactive flow:
  1. User sends URL → Bot fetches metadata
  2. Bot shows quality selection (inline keyboard)
  3. User taps quality → Bot shows audio selection
  4. User taps audio → Bot shows subtitle selection
  5. User taps subtitle → Bot downloads & uploads

Commands:
  /start   – Welcome message
  /leech   – Download a video
  /cancel  – Cancel active download
  /help    – Help text
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
from downloader import VideoInfo, download, fetch_info
from platforms import detect_platform
from uploader import upload_file
from utils import (
    extract_url,
    format_progress_card,
    human_duration,
    human_size,
    is_supported_url,
    progress_bar,
)


# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("LeechBot")

# ── Pyrogram client ───────────────────────────────────────────────────────────
app = Client(
    name="LeechBotV2",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    workers=4,
)



# ── Session tracking ──────────────────────────────────────────────────────────

@dataclass
class SelectionSession:
    """Tracks a user's in-progress format selection."""
    url: str
    info: VideoInfo
    platform: object          # Platform instance
    status_msg: Message
    custom_rename: Optional[str] = None
    selected_quality_id: Optional[str] = None
    selected_quality_label: Optional[str] = None
    selected_audio_id: Any = None
    selected_audio_label: Optional[str] = None
    selected_audio_indices: set[int] = field(default_factory=set)
    selected_subs: list[str] = field(default_factory=list)




_sessions: dict[int, SelectionSession] = {}       # user_id → session
_active_tasks: dict[int, asyncio.Task] = {}        # user_id → download task


# ── Access-control filter ─────────────────────────────────────────────────────
def _allowed(_, __, msg) -> bool:
    if not config.ALLOWED_USERS:
        return True
    return msg.from_user is not None and msg.from_user.id in config.ALLOWED_USERS

allowed = filters.create(_allowed)


# ═════════════════════════════════════════════════════════════════════════════
# COMMANDS
# ═════════════════════════════════════════════════════════════════════════════

@app.on_message(filters.command("start") & allowed)
async def cmd_start(client: Client, message: Message):
    await message.reply_text(
        "👋 **Welcome to the Leech Bot V2!**\n\n"
        "I can download videos from **JioHotstar** 🟢 and **MX Player** 🔵 "
        "and send them directly to you on Telegram.\n\n"
        "**How to use**\n"
        "1️⃣  Send me a JioHotstar or MX Player link\n"
        "2️⃣  Choose quality, audio language, and subtitles\n"
        "3️⃣  I'll download and send the video!\n\n"
        "**Commands**\n"
        "• `/leech <url>` – Download a video\n"
        "• `/cancel`      – Cancel active download\n"
        "• `/help`        – Show this help\n\n"
        f"📦 Max upload: `{config.MAX_FILESIZE_BYTES // (1024**2)} MB`",
        disable_web_page_preview=True,
    )


@app.on_message(filters.command("help") & allowed)
async def cmd_help(client: Client, message: Message):
    await cmd_start(client, message)


@app.on_message(filters.command("cancel") & allowed)
async def cmd_cancel(client: Client, message: Message):
    user_id = message.from_user.id
    # Cancel download task
    task = _active_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()
    # Clear session
    _sessions.pop(user_id, None)
    await message.reply_text("🚫 Cancelled.")


# ═════════════════════════════════════════════════════════════════════════════
# /leech COMMAND + PLAIN URL
# ═════════════════════════════════════════════════════════════════════════════

def _parse_url_and_options(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse URL and optional custom title via -n flag.
    Example: `/leech https://www.mxplayer.in/... -n My Custom Title`
    """
    url = extract_url(text)
    if not url:
        return None, None

    custom_title = None
    if "-n" in text:
        parts = text.split("-n", 1)
        if len(parts) > 1:
            raw_title = parts[1].strip()
            if raw_title:
                custom_title = raw_title.split(" -")[0].strip()

    return url, custom_title if custom_title else None


@app.on_message(filters.command("leech") & allowed)
async def cmd_leech(client: Client, message: Message):
    user_id = message.from_user.id

    if user_id in _active_tasks:
        await message.reply_text(
            "⚠️ You already have a download in progress.\n"
            "Use `/cancel` to abort it first."
        )
        return

    url, custom_rename = _parse_url_and_options(message.text or "")

    if not url or not is_supported_url(url):
        await message.reply_text(
            "❌ Please provide a valid **JioHotstar** or **MX Player** URL.\n\n"
            "Usage: `/leech https://www.hotstar.com/...`\n"
            "       `/leech https://www.mxplayer.in/... -n Custom Title`"
        )
        return

    await _start_selection(client, message, url, user_id, custom_rename=custom_rename)


@app.on_message(
    filters.text & allowed
    & ~filters.command(["start", "help", "leech", "cancel"])
)
async def handle_plain_url(client: Client, message: Message):
    """Auto-detect supported URLs pasted without a command."""
    url, custom_rename = _parse_url_and_options(message.text or "")
    if url:
        user_id = message.from_user.id
        if user_id in _active_tasks:
            await message.reply_text("⚠️ Download already in progress. Use `/cancel` first.")
            return
        await _start_selection(client, message, url, user_id, custom_rename=custom_rename)


# ═════════════════════════════════════════════════════════════════════════════
# SELECTION FLOW
# ═════════════════════════════════════════════════════════════════════════════

async def _start_selection(
    client: Client,
    message: Message,
    url: str,
    user_id: int,
    custom_rename: Optional[str] = None,
):
    """Phase 0: Fetch metadata and show quality selection."""
    platform = detect_platform(url)
    if not platform:
        await message.reply_text("❌ URL not recognized as JioHotstar or MX Player.")
        return

    status = await message.reply_text(
        f"{platform.icon} **{platform.name}** detected\n\n"
        f"🔍 Fetching video info…"
    )

    try:
        info = await fetch_info(url, platform)
        if custom_rename:
            info.title = custom_rename
    except Exception as exc:
        log.exception("Info fetch failed for %s", url)
        await status.edit_text(f"❌ Failed to fetch info:\n`{exc}`")
        return

    # Store session
    session = SelectionSession(
        url=url,
        info=info,
        platform=platform,
        status_msg=status,
        custom_rename=custom_rename,
    )
    _sessions[user_id] = session


    # Build header
    header = (
        f"{platform.icon} **{info.title}**\n\n"
        f"⏱ Duration: `{human_duration(info.duration)}`\n"
        f"👤 Source: `{info.uploader or 'N/A'}`\n"
    )

    # Show quality selection (or skip if only one / none)
    if len(info.qualities) == 0:
        # No parseable qualities — use best available
        session.selected_quality_id = "bestvideo"
        session.selected_quality_label = "Best"
        await _show_audio_selection(user_id, status, header)
    elif len(info.qualities) == 1:
        # Only one quality — auto-select
        q = info.qualities[0]
        session.selected_quality_id = q.format_id
        session.selected_quality_label = q.label
        await _show_audio_selection(user_id, status, header)
    else:
        # Multiple qualities — show buttons
        buttons = []
        row = []
        for idx, q in enumerate(info.qualities):
            size_hint = f" (~{human_size(q.filesize_approx)})" if q.filesize_approx else ""
            text = f"📺 {q.label}{size_hint}"
            row.append(InlineKeyboardButton(text, callback_data=f"q|{user_id}|{idx}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        await status.edit_text(
            header + "\n📺 **Select Video Quality:**",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


async def _show_audio_selection(user_id: int, status: Message, header: str):
    """Phase 2: Show multi-select audio language buttons."""
    session = _sessions.get(user_id)
    if not session:
        return

    info = session.info

    if len(info.audio_tracks) == 0:
        # No separate audio tracks — use default
        session.selected_audio_id = None
        session.selected_audio_label = "Default"
        await _show_subtitle_selection(user_id, status, header)
    elif len(info.audio_tracks) == 1:
        # Only one audio — auto-select
        a = info.audio_tracks[0]
        session.selected_audio_id = a.format_id or None
        session.selected_audio_label = a.label
        await _show_subtitle_selection(user_id, status, header)
    else:
        buttons = []
        row = []
        for idx, a in enumerate(info.audio_tracks):
            is_selected = idx in session.selected_audio_indices
            icon = "✅" if is_selected else "🔊"
            text = f"{icon} {a.label}"
            row.append(InlineKeyboardButton(text, callback_data=f"a|{user_id}|{idx}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        # Control buttons matching user design
        buttons.append([
            InlineKeyboardButton("Done / Start", callback_data=f"a|{user_id}|done"),
            InlineKeyboardButton("Skip Audio", callback_data=f"a|{user_id}|skip"),
            InlineKeyboardButton("Cancel", callback_data=f"a|{user_id}|cancel"),
        ])

        summary = f"📺 Quality: `{session.selected_quality_label}`\n"
        await status.edit_text(
            header + summary + "\n🎵 **Select one or more audio languages:**",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


async def _show_subtitle_selection(user_id: int, status: Message, header: str):
    """Phase 3: Show subtitle buttons."""
    session = _sessions.get(user_id)
    if not session:
        return

    info = session.info

    if len(info.subtitle_tracks) == 0:
        # No subtitles available — skip to download
        session.selected_subs = []
        await _begin_download(user_id, status, header)
    else:
        buttons = []
        row = []
        for idx, s in enumerate(info.subtitle_tracks):
            text = f"🔤 {s.label}"
            row.append(InlineKeyboardButton(text, callback_data=f"s|{user_id}|{idx}"))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        # Add "No subtitles" button
        buttons.append([InlineKeyboardButton("❌ No Subtitles", callback_data=f"s|{user_id}|none")])

        summary = (
            f"📺 Quality: `{session.selected_quality_label}`\n"
            f"🔊 Audio: `{session.selected_audio_label}`\n"
        )
        await status.edit_text(
            header + summary + "\n🔤 **Select Subtitles:**",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


# ═════════════════════════════════════════════════════════════════════════════
# CALLBACK QUERY HANDLERS
# ═════════════════════════════════════════════════════════════════════════════

@app.on_callback_query(filters.regex(r"^q\|"))
async def cb_quality(client: Client, cb: CallbackQuery):
    """User tapped a quality button."""
    _, uid_str, idx_str = cb.data.split("|", 2)
    user_id = int(uid_str)

    if cb.from_user.id != user_id:
        await cb.answer("❌ This isn't your selection.", show_alert=True)
        return

    session = _sessions.get(user_id)
    if not session:
        await cb.answer("Session expired. Send the URL again.", show_alert=True)
        return

    idx = int(idx_str)
    if idx < 0 or idx >= len(session.info.qualities):
        await cb.answer("Invalid selection.", show_alert=True)
        return

    q = session.info.qualities[idx]
    session.selected_quality_id = q.format_id
    session.selected_quality_label = q.label
    await cb.answer(f"Quality: {q.label} ✓")

    header = (
        f"{session.platform.icon} **{session.info.title}**\n\n"
        f"⏱ Duration: `{human_duration(session.info.duration)}`\n"
        f"👤 Source: `{session.info.uploader or 'N/A'}`\n"
    )
    await _show_audio_selection(user_id, session.status_msg, header)


@app.on_callback_query(filters.regex(r"^a\|"))
async def cb_audio(client: Client, cb: CallbackQuery):
    """User tapped an audio language checkbox or control button."""
    _, uid_str, action = cb.data.split("|", 2)
    user_id = int(uid_str)

    if cb.from_user.id != user_id:
        await cb.answer("❌ This isn't your selection.", show_alert=True)
        return

    session = _sessions.get(user_id)
    if not session:
        await cb.answer("Session expired. Send the URL again.", show_alert=True)
        return

    header = (
        f"{session.platform.icon} **{session.info.title}**\n\n"
        f"⏱ Duration: `{human_duration(session.info.duration)}`\n"
        f"👤 Source: `{session.info.uploader or 'N/A'}`\n"
    )

    if action == "done":
        if not session.selected_audio_indices:
            # Default to all tracks if none explicitly selected
            selected_tracks = session.info.audio_tracks
        else:
            selected_tracks = [session.info.audio_tracks[i] for i in sorted(session.selected_audio_indices)]

        session.selected_audio_id = [a.format_id for a in selected_tracks if a.format_id]
        session.selected_audio_label = ", ".join([a.label for a in selected_tracks]) or "All Languages"
        await cb.answer("Audio selection saved ✓")
        await _show_subtitle_selection(user_id, session.status_msg, header)

    elif action == "skip":
        session.selected_audio_id = None
        session.selected_audio_label = "Default"
        await cb.answer("Audio skipped ✓")
        await _show_subtitle_selection(user_id, session.status_msg, header)

    elif action == "cancel":
        _sessions.pop(user_id, None)
        await cb.answer("Cancelled")
        await session.status_msg.edit_text("🚫 Selection cancelled.")

    else:
        # Toggle language index
        idx = int(action)
        if 0 <= idx < len(session.info.audio_tracks):
            if idx in session.selected_audio_indices:
                session.selected_audio_indices.remove(idx)
                await cb.answer(f"Deselected {session.info.audio_tracks[idx].label}")
            else:
                session.selected_audio_indices.add(idx)
                await cb.answer(f"Selected {session.info.audio_tracks[idx].label} ✓")
            await _show_audio_selection(user_id, session.status_msg, header)




@app.on_callback_query(filters.regex(r"^s\|"))
async def cb_subtitle(client: Client, cb: CallbackQuery):
    """User tapped a subtitle button."""
    _, uid_str, idx_str = cb.data.split("|", 2)
    user_id = int(uid_str)

    if cb.from_user.id != user_id:
        await cb.answer("❌ This isn't your selection.", show_alert=True)
        return

    session = _sessions.get(user_id)
    if not session:
        await cb.answer("Session expired. Send the URL again.", show_alert=True)
        return

    if idx_str == "none":
        session.selected_subs = []
        await cb.answer("Subtitles: None ✓")
    else:
        idx = int(idx_str)
        if idx < 0 or idx >= len(session.info.subtitle_tracks):
            await cb.answer("Invalid selection.", show_alert=True)
            return
        s = session.info.subtitle_tracks[idx]
        session.selected_subs = [s.lang_code]
        await cb.answer(f"Subtitles: {s.label} ✓")

    header = (
        f"{session.platform.icon} **{session.info.title}**\n\n"
        f"⏱ Duration: `{human_duration(session.info.duration)}`\n"
        f"👤 Source: `{session.info.uploader or 'N/A'}`\n"
    )
    await _begin_download(user_id, session.status_msg, header)

# ═════════════════════════════════════════════════════════════════════════════
# DOWNLOAD + UPLOAD PIPELINE
# ═════════════════════════════════════════════════════════════════════════════


async def _begin_download(user_id: int, status: Message, header: str):
    """Start the download→upload pipeline with the user's selections."""
    session = _sessions.get(user_id)
    if not session:
        return

    summary = (
        f"📺 Quality: `{session.selected_quality_label}`\n"
        f"🔊 Audio: `{session.selected_audio_label}`\n"
        f"🔤 Subtitles: `{', '.join(session.selected_subs) if session.selected_subs else 'None'}`\n"
    )
    await status.edit_text(
        header + summary + "\n⏳ **Starting download…**",
        reply_markup=None,
    )

    task = asyncio.create_task(
        _download_and_upload(user_id, session, status, header, summary)
    )
    _active_tasks[user_id] = task

    def _cleanup(t):
        _active_tasks.pop(user_id, None)
        _sessions.pop(user_id, None)

    task.add_done_callback(_cleanup)


async def _download_and_upload(
    user_id: int,
    session: SelectionSession,
    status: Message,
    header: str,
    summary: str,
):
    """Core download → upload pipeline."""
    dest_dir = config.DOWNLOAD_DIR / str(user_id)
    file_path: Path | None = None

    user_name = status.chat.first_name or status.chat.title or "User"
    user_id_val = status.chat.id

    try:
        # ── Download ──────────────────────────────────────────────────────────
        _dl_last = [0.0]

        async def _dl_progress(downloaded: int, total: int, speed: float):
            now = time.monotonic()
            if now - _dl_last[0] < 2.0:
                return
            _dl_last[0] = now

            card = format_progress_card(
                title=session.info.title,
                user_name=user_name,
                user_id=user_id_val,
                current_bytes=downloaded,
                total_bytes=total,
                speed_bytes_sec=speed,
                status_label="Downloading",
                quality=session.selected_quality_label or "Best",
                audio=session.selected_audio_label or "Default",
            )
            try:
                await status.edit_text(card, reply_markup=None)
            except Exception:
                pass

        try:
            file_path = await download(
                url=session.url,
                dest_dir=dest_dir,
                platform=session.platform,
                video_format_id=session.selected_quality_id or "bestvideo",
                audio_format_id=session.selected_audio_id,
                subtitle_langs=session.selected_subs if session.selected_subs else None,
                progress_cb=_dl_progress,
            )
        except asyncio.CancelledError:
            await status.edit_text("🚫 Download cancelled.")
            return
        except ValueError as exc:
            await status.edit_text(f"❌ {exc}")
            return
        except Exception as exc:
            log.exception("Download failed for %s", session.url)
            await status.edit_text(f"❌ Download failed:\n`{exc}`")
            return

        actual_size = file_path.stat().st_size

        # ── Upload ────────────────────────────────────────────────────────────
        caption = (
            f"{session.platform.icon} **{session.info.title}**\n"
            f"⏱ `{human_duration(session.info.duration)}`\n"
            f"📺 `{session.selected_quality_label}` • "
            f"🔊 `{session.selected_audio_label}`\n"
            f"📦 `{human_size(actual_size)}`"
        )
        try:
            await upload_file(
                client=app,
                chat_id=status.chat.id,
                file_path=file_path,
                caption=caption,
                status_msg=status,
                user_name=user_name,
                user_id=user_id_val,
                quality=session.selected_quality_label or "Best",
                audio=session.selected_audio_label or "Default",
            )
        except asyncio.CancelledError:
            await status.edit_text("🚫 Upload cancelled.")
            return
        except Exception as exc:
            log.exception("Upload failed for %s", file_path)
            await status.edit_text(f"❌ Upload failed:\n`{exc}`")
            return


        # ── Google Drive Upload ────────────────────────────────────────────────
        gdrive_url = None
        _gd_last = [0.0]
        _gd_start = time.monotonic()

        def _gd_progress(current: int, total: int):
            now = time.monotonic()
            if now - _gd_last[0] < 3.0:
                return
            _gd_last[0] = now
            elapsed = max(now - _gd_start, 0.1)
            speed = current / elapsed
            card = format_progress_card(
                title=session.info.title,
                user_name=user_name,
                user_id=user_id_val,
                current_bytes=current,
                total_bytes=total,
                speed_bytes_sec=speed,
                status_label="Uploading to Google Drive",
                quality=session.selected_quality_label or "Best",
                audio=session.selected_audio_label or "Default",
            )
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(status.edit_text(card))
                )
            except Exception:
                pass

        try:
            from gdrive import upload_to_gdrive
            gdrive_url = upload_to_gdrive(file_path, progress_cb=_gd_progress)
        except Exception as exc:
            log.warning("Google Drive upload attempt skipped/failed: %s", exc)

        gdrive_txt = f"\n\n📂 **Google Drive Link**: [Open File in Google Drive]({gdrive_url})" if gdrive_url else ""

        await status.edit_text(
            f"✅ **Done!** `{session.info.title}` processing & upload complete. 🎉{gdrive_txt}"
        )



    finally:
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                log.info("Cleaned up %s", file_path)
            except OSError:
                pass
        if dest_dir.exists():
            try:
                dest_dir.rmdir()
            except OSError:
                pass


from time_sync import apply_pyrogram_fix

if __name__ == "__main__":
    log.info("Starting Leech Bot V2…")
    apply_pyrogram_fix()
    app.run()

