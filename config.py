"""
config.py – Load and validate all environment variables for V2.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example -> .env and fill in your values."
        )
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN: str = _require("BOT_TOKEN")
API_ID: int = int(_require("API_ID"))
API_HASH: str = _require("API_HASH")

# ── Access Control ─────────────────────────────────────────────────────────────
_raw_users = _optional("ALLOWED_USERS")
ALLOWED_USERS: set[int] = (
    {int(u.strip()) for u in _raw_users.split(",") if u.strip()}
    if _raw_users
    else set()
)

# ── Dump chat ─────────────────────────────────────────────────────────────────
_dump = _optional("DUMP_CHAT_ID")
DUMP_CHAT_ID: int | None = int(_dump) if _dump else None

# ── Cookies (per platform, loaded via platforms module) ────────────────────────
# JIOHOTSTAR_COOKIES and MXPLAYER_COOKIES are read by their respective
# platform handlers via os.getenv() — no need to centralize here.

# ── Download settings ─────────────────────────────────────────────────────────
DOWNLOAD_DIR: Path = Path(_optional("DOWNLOAD_DIR", "./downloads"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILESIZE_BYTES: int = int(_optional("MAX_FILESIZE_MB", "1900")) * 1024 * 1024

# ── Google Drive Mirroring ────────────────────────────────────────────────────
GDRIVE_FOLDER_ID: str = _optional("GDRIVE_FOLDER_ID", "1SQXO4uP3EWdhaAc8D907g1P3YgEhCVqR")
GDRIVE_SA_FILE: Path = Path(_optional("GDRIVE_SA_FILE", "./service_account.json"))

