"""
downloader.py – Unified yt-dlp wrapper for JioHotstar & MX Player.

Key features:
  - Enriched VideoInfo with parsed quality, audio, and subtitle tracks
  - Format selection based on user choices
  - Async download with progress callback
"""
import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import yt_dlp

import config
from utils import human_size


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class QualityOption:
    """Represents a selectable video quality."""
    format_id: str          # yt-dlp format ID
    height: int             # e.g. 1080, 720
    label: str              # e.g. "1080p"
    codec: str              # e.g. "avc1", "hevc"
    filesize_approx: int    # bytes (0 if unknown)
    fps: int = 0


@dataclass
class AudioTrack:
    """Represents a selectable audio track."""
    format_id: str          # yt-dlp format ID
    language: str           # e.g. "hin", "eng", "tam"
    label: str              # e.g. "Hindi", "English"
    codec: str
    filesize_approx: int


@dataclass
class SubtitleTrack:
    """Represents an available subtitle language."""
    lang_code: str          # e.g. "en", "hi"
    label: str              # e.g. "English", "Hindi"


@dataclass
class VideoInfo:
    """Enriched video metadata from yt-dlp."""
    title: str
    duration: int                                  # seconds
    thumbnail: Optional[str]
    uploader: Optional[str]
    platform: str                                  # "JioHotstar" / "MX Player"
    url: str
    qualities: list[QualityOption] = field(default_factory=list)
    audio_tracks: list[AudioTrack] = field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = field(default_factory=list)
    raw_formats: list[dict] = field(default_factory=list)


# ── Language code → human label ───────────────────────────────────────────────

_LANG_NAMES = {
    "hin": "Hindi", "hi": "Hindi",
    "eng": "English", "en": "English",
    "tam": "Tamil", "ta": "Tamil",
    "tel": "Telugu", "te": "Telugu",
    "kan": "Kannada", "kn": "Kannada",
    "mal": "Malayalam", "ml": "Malayalam",
    "mar": "Marathi", "mr": "Marathi",
    "ben": "Bengali", "bn": "Bengali",
    "guj": "Gujarati", "gu": "Gujarati",
    "pan": "Punjabi", "pa": "Punjabi",
    "ori": "Odia", "or": "Odia",
    "urd": "Urdu", "ur": "Urdu",
    "und": "Unknown",
}


def _lang_label(code: str) -> str:
    """Convert a language code to a human-readable label."""
    if not code:
        return "Unknown"
    return _LANG_NAMES.get(code.lower(), code.upper())


# ── yt-dlp option builder ─────────────────────────────────────────────────────

def _build_opts(platform=None) -> dict:
    """Build base yt-dlp options, optionally with platform-specific settings."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "concurrent_fragment_downloads": 16,  # 16 parallel segment downloads
        "buffersize": 4 * 1024 * 1024,        # 4 MB memory buffer
        "http_chunk_size": 10485760,           # 10 MB HTTP chunks
        "retries": 15,
        "fragment_retries": 15,
        "socket_timeout": 30,
    }

    # Auto-detect aria2c binary for ultra-fast multi-connection download
    aria2_path = Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\aria2c.exe"))
    if aria2_path.exists():
        opts["external_downloader"] = {"default": str(aria2_path)}
        opts["external_downloader_args"] = {
            "default": ["-x16", "-s16", "-k1M", "--min-split-size=1M"]
        }

    # Auto-detect FFmpeg binary via imageio_ffmpeg
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_exe:
            opts["ffmpeg_location"] = ffmpeg_exe
    except Exception:
        pass

    if platform:
        opts.update(platform.get_extra_opts())
        cookie_file = platform.get_cookie_file()
        if cookie_file:
            opts["cookiefile"] = str(cookie_file)

    return opts





# ── Format parsing ────────────────────────────────────────────────────────────

def _parse_formats(raw_formats: list[dict], subtitles_dict: dict) -> tuple[
    list[QualityOption], list[AudioTrack], list[SubtitleTrack]
]:
    """
    Parse raw yt-dlp format list into structured quality, audio, subtitle options.
    De-duplicates by height (qualities) and language (audio).
    """
    qualities: dict[int, QualityOption] = {}
    audio_tracks: dict[str, AudioTrack] = {}

    for fmt in raw_formats:
        vcodec = fmt.get("vcodec", "none")
        acodec = fmt.get("acodec", "none")
        height = fmt.get("height") or 0
        lang = fmt.get("language") or ""
        fmt_id = fmt.get("format_id", "")
        filesize = fmt.get("filesize") or fmt.get("filesize_approx") or 0

        # Video-only or video+audio formats
        if vcodec != "none" and height > 0:
            # Keep the best (largest filesize) for each height
            if height not in qualities or filesize > qualities[height].filesize_approx:
                qualities[height] = QualityOption(
                    format_id=fmt_id,
                    height=height,
                    label=f"{height}p",
                    codec=vcodec.split(".")[0] if vcodec else "?",
                    filesize_approx=filesize,
                    fps=fmt.get("fps") or 0,
                )

        # Audio-only formats
        if acodec != "none" and vcodec == "none" and lang:
            lang_key = lang.lower()[:3]
            if lang_key not in audio_tracks or filesize > audio_tracks[lang_key].filesize_approx:
                audio_tracks[lang_key] = AudioTrack(
                    format_id=fmt_id,
                    language=lang_key,
                    label=_lang_label(lang_key),
                    codec=acodec.split(".")[0] if acodec else "?",
                    filesize_approx=filesize,
                )

    # If no separate audio tracks found, look for combined formats
    if not audio_tracks:
        for fmt in raw_formats:
            acodec = fmt.get("acodec", "none")
            vcodec = fmt.get("vcodec", "none")
            lang = fmt.get("language") or ""
            if acodec != "none" and vcodec != "none" and lang:
                lang_key = lang.lower()[:3]
                if lang_key not in audio_tracks:
                    audio_tracks[lang_key] = AudioTrack(
                        format_id="",  # Will use combined format
                        language=lang_key,
                        label=_lang_label(lang_key),
                        codec=acodec.split(".")[0] if acodec else "?",
                        filesize_approx=0,
                    )

    # Subtitles
    subs: list[SubtitleTrack] = []
    for lang_code in sorted(subtitles_dict.keys()):
        if lang_code in ("live_chat",):
            continue
        subs.append(SubtitleTrack(
            lang_code=lang_code,
            label=_lang_label(lang_code),
        ))

    # Sort qualities descending
    sorted_qualities = sorted(qualities.values(), key=lambda q: q.height, reverse=True)
    sorted_audio = sorted(audio_tracks.values(), key=lambda a: a.label)

    return sorted_qualities, sorted_audio, subs


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_info(url: str, platform=None) -> VideoInfo:
    """
    Fetch video metadata without downloading.
    Returns an enriched VideoInfo with parsed quality/audio/subtitle options.
    """
    opts = _build_opts(platform)
    opts["skip_download"] = True

    def _run():
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as err:
            err_str = str(err)
            if "API call was unsuccessful" in err_str or "registered users" in err_str:
                raise RuntimeError(
                    "🍪 **Hotstar Session / Cookie Error**\n\n"
                    "Your Hotstar account was **logged out** (likely due to exceeding device limit) "
                    "or your cookies file has expired.\n\n"
                    "**To Fix:**\n"
                    "1. Open Hotstar in your browser & sign back in.\n"
                    "2. Export a fresh `cookies.txt` using the extension.\n"
                    "3. Replace `hotstar.com_cookies.txt.txt` in your bot folder."
                ) from err
            raise

    loop = asyncio.get_event_loop()
    info = await loop.run_in_executor(None, _run)


    raw_formats = info.get("formats", [])
    subtitles_dict = info.get("subtitles", {})
    automatic_captions = info.get("automatic_captions", {})
    # Merge automatic captions into subtitles
    for k, v in automatic_captions.items():
        if k not in subtitles_dict:
            subtitles_dict[k] = v

    qualities, audio_tracks, subtitle_tracks = _parse_formats(raw_formats, subtitles_dict)

    return VideoInfo(
        title=info.get("title", "Unknown"),
        duration=int(info.get("duration", 0)),
        thumbnail=info.get("thumbnail"),
        uploader=info.get("uploader") or info.get("channel"),
        platform=platform.name if platform else "Unknown",
        url=url,
        qualities=qualities,
        audio_tracks=audio_tracks,
        subtitle_tracks=subtitle_tracks,
        raw_formats=raw_formats,
    )


def _build_format_string(
    video_format_id: str,
    audio_format_ids: str | list[str] | None,
) -> str:
    """Build yt-dlp format string from user selections."""
    if audio_format_ids == "all":
        return f"{video_format_id}+all[acodec!=none]/{video_format_id}+bestaudio/best"
    elif isinstance(audio_format_ids, list) and audio_format_ids:
        audio_part = "+".join(audio_format_ids)
        return f"{video_format_id}+{audio_part}/best"
    elif isinstance(audio_format_ids, str) and audio_format_ids:
        return f"{video_format_id}+{audio_format_ids}/best"
    return f"{video_format_id}+bestaudio/best"



async def download(
    url: str,
    dest_dir: Path,
    platform=None,
    video_format_id: str = "bestvideo",
    audio_format_id: Optional[str] = None,
    subtitle_langs: Optional[list[str]] = None,
    progress_cb: Optional[Callable] = None,
) -> Path:
    """
    Download a video with the user's selected quality/audio/subtitles.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    output_tmpl = str(dest_dir / "%(title).100s.%(ext)s")

    downloaded_file: list[Path] = []
    _last_call = [0.0]

    def _hook(d: dict):
        if d["status"] == "finished":
            fn = Path(d["filename"])
            if fn.suffix.lower() not in (".vtt", ".srt", ".ass", ".part", ".ytdl"):
                downloaded_file.append(fn)
        elif d["status"] == "downloading" and progress_cb is not None:
            now = time.monotonic()
            if now - _last_call[0] < 2.0:
                return
            _last_call[0] = now
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            speed = d.get("speed") or 0.0
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(
                    lambda dl=downloaded, t=total, s=speed: asyncio.ensure_future(
                        _safe_cb(progress_cb, dl, t, s)
                    )
                )
            except RuntimeError:
                pass

    format_str = _build_format_string(video_format_id, audio_format_id)

    # Use MKV container if 'all' audio tracks or subtitles selected
    merge_fmt = "mkv" if (audio_format_id == "all" or subtitle_langs) else "mp4"

    opts = _build_opts(platform)
    opts.update({
        "format": format_str,
        "outtmpl": output_tmpl,
        "merge_output_format": merge_fmt,
        "postprocessor_args": {
            "ffmpeg": ["-c:v", "copy", "-c:a", "copy", "-c:s", "copy"],
            "FFmpegEmbedSubtitle": ["-c:v", "copy", "-c:a", "copy", "-c:s", "copy"],
        },
        "progress_hooks": [_hook],
        "noprogress": True,
    })




    # Subtitles
    if subtitle_langs:
        opts.update({
            "writesubtitles": True,
            "subtitleslangs": subtitle_langs,
            "embedsubtitles": True,
            "postprocessors": [
                {
                    "key": "FFmpegEmbedSubtitle",
                    "already_have_subtitle": False,
                }
            ],
        })

    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run)

    # Find the final video file in dest_dir
    video_files = [
        f for f in dest_dir.iterdir()
        if f.is_file() and f.suffix.lower() in (".mp4", ".mkv", ".webm", ".avi", ".ts", ".mov")
    ]
    if video_files:
        video_files.sort(key=os.path.getmtime, reverse=True)
        path = video_files[0]
    elif downloaded_file and downloaded_file[0].exists():
        path = downloaded_file[0]
    else:
        files = [f for f in dest_dir.iterdir() if f.is_file()]
        if not files:
            raise RuntimeError("Download completed but no output file was found.")
        files.sort(key=os.path.getmtime, reverse=True)
        path = files[0]

    # Size guard
    size = path.stat().st_size

    if size > config.MAX_FILESIZE_BYTES:
        path.unlink(missing_ok=True)
        raise ValueError(
            f"File is too large to upload: {human_size(size)} "
            f"(limit {human_size(config.MAX_FILESIZE_BYTES)})"
        )

    return path


async def _safe_cb(cb, *args):
    try:
        await cb(*args)
    except Exception:
        pass
