from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from trading_bot.config import SessionConfig


class SessionFilter:
    """Checks whether current time sits inside the configured London session."""

    def __init__(self, config: SessionConfig):
        self.config = config
        self._tz = ZoneInfo(config.timezone)

    def in_session(self, now: datetime) -> bool:
        aware = now.astimezone(self._tz)
        session_start = aware.replace(
            hour=self.config.start.hour,
            minute=self.config.start.minute,
            second=0,
            microsecond=0,
        )
        session_end = aware.replace(
            hour=self.config.end.hour,
            minute=self.config.end.minute,
            second=0,
            microsecond=0,
        )
        return session_start <= aware <= session_end

    def past_session(self, now: datetime) -> bool:
        return not self.in_session(now)
