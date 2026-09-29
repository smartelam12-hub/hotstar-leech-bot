"""
hotstar.py – JioHotstar platform handler.
"""
import os
from pathlib import Path
from typing import Optional
from platforms.base import Platform


class HotstarPlatform(Platform):

    @property
    def name(self) -> str:
        return "JioHotstar"

    @property
    def domains(self) -> list[str]:
        return [
            "hotstar.com",
            "jiohotstar.com",
            "disneyplus.hotstar.com",
            "hss.hotstar.com",
        ]

    @property
    def icon(self) -> str:
        return "🟢"

    def get_cookie_file(self) -> Optional[Path]:
        path_str = os.getenv("JIOHOTSTAR_COOKIES", "").strip()
        if path_str:
            p = Path(path_str)
            if p.exists():
                return p
        return None

    def get_extra_opts(self) -> dict:
        return {
            "geo_bypass": True,
            "geo_bypass_country": "IN",
        }
