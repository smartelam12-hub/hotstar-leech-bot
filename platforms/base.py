"""
base.py – Abstract Platform interface.
"""
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class Platform(ABC):
    """Base class for a supported streaming platform."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name (e.g. 'JioHotstar')."""
        ...

    @property
    @abstractmethod
    def domains(self) -> list[str]:
        """List of domain patterns this platform matches."""
        ...

    @property
    @abstractmethod
    def icon(self) -> str:
        """Emoji icon for this platform."""
        ...

    def matches(self, url: str) -> bool:
        """Return True if *url* belongs to this platform."""
        url_lower = url.lower().strip()
        return any(d in url_lower for d in self.domains)

    @abstractmethod
    def get_cookie_file(self) -> Optional[Path]:
        """Return path to cookie file for this platform, or None."""
        ...

    @abstractmethod
    def get_extra_opts(self) -> dict:
        """Return extra yt-dlp options specific to this platform."""
        ...
