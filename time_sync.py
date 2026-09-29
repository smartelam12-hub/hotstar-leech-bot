"""
time_sync.py – Fix Pyrogram's MTProto time sync issue.

Telegram's MTProto protocol requires the client clock to be within ~30s of
the server. If the system clock is off, Pyrogram fails with BadMsgNotification [17].

This module queries an NTP server, computes the offset, and patches `time.time`
globally so that Pyrogram generates valid `msg_id` timestamps.
"""
import logging
import time

log = logging.getLogger("LeechBot.TimeSync")

_time_offset: float = 0.0
_original_time = time.time


def detect_offset() -> float:
    """
    Query NTP to find how far off the system clock is.
    Returns the offset in seconds (negative = clock is ahead).
    """
    global _time_offset
    try:
        import ntplib
        client = ntplib.NTPClient()
        response = client.request("pool.ntp.org", version=3)
        _time_offset = response.offset
        direction = "ahead" if _time_offset < 0 else "behind"
        log.info(
            "System clock is %.1fs %s of NTP time (offset=%.2f)",
            abs(_time_offset), direction, _time_offset,
        )
        return _time_offset
    except Exception as e:
        log.warning("NTP query failed (%s). Time offset not corrected.", e)
        return 0.0


def apply_pyrogram_fix():
    """
    Globally patch `time.time` to apply the NTP time offset to all Pyrogram
    msg_id calculations, preventing BadMsgNotification [17] errors.
    """
    offset = detect_offset()
    if abs(offset) < 3.0:
        log.info("Clock offset is small (%.1fs), no patch needed.", offset)
        return

    def _corrected_time() -> float:
        return _original_time() + _time_offset

    # Global patch
    time.time = _corrected_time

    # Specific module patches for extra safety
    try:
        import pyrogram.session.internals.msg_id as msg_id_mod
        msg_id_mod.time.time = _corrected_time
    except Exception:
        pass

    log.info("Applied NTP time correction (offset=%.2fs) to time.time", _time_offset)
