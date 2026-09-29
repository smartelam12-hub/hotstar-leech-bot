"""
platforms – URL-to-platform routing.
"""
from platforms.hotstar import HotstarPlatform
from platforms.mxplayer import MxPlayerPlatform
from platforms.base import Platform

_PLATFORMS: list[Platform] = [
    HotstarPlatform(),
    MxPlayerPlatform(),
]


def detect_platform(url: str) -> Platform | None:
    """Return the Platform that matches *url*, or None."""
    for p in _PLATFORMS:
        if p.matches(url):
            return p
    return None


def supported_domains() -> list[str]:
    """Return a flat list of all supported domain patterns."""
    domains = []
    for p in _PLATFORMS:
        domains.extend(p.domains)
    return domains
