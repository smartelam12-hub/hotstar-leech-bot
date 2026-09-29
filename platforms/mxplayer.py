"""
mxplayer.py – MX Player platform handler.
"""
import os
from pathlib import Path
from typing import Optional
from platforms.base import Platform


class MxPlayerPlatform(Platform):

    @property
    def name(self) -> str:
        return "MX Player"

    @property
    def domains(self) -> list[str]:
        return [
            "mxplayer.in",
            "mxplayer.com",
        ]

    @property
    def icon(self) -> str:
        return "🔵"

    def get_cookie_file(self) -> Optional[Path]:
        path_str = os.getenv("MXPLAYER_COOKIES", "").strip()
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
