from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List

from trading_bot.config import NewsConfig, NewsEvent


@dataclass
class NewsWindow:
    title: str
    start: datetime
    end: datetime

    def active(self, now: datetime) -> bool:
        return self.start <= now <= self.end


class NewsFilter:
    """Enforces high-impact news blackouts using configured windows."""

    def __init__(self, config: NewsConfig):
        self.config = config
        self._windows: List[NewsWindow] = []

    def load_from_calendar(self, anchor: datetime, events: Iterable[NewsEvent]) -> None:
        self._windows.clear()
        for event in events:
            start = anchor + event.start_offset - timedelta(
                minutes=self.config.blackout_minutes_before
            )
            end = anchor + event.end_offset + timedelta(
                minutes=self.config.blackout_minutes_after
            )
            self._windows.append(NewsWindow(event.title, start, end))

    def sync(self, now: datetime) -> None:
        """Refresh blackout windows from the static config (stub for live feeds)."""
        if not self._windows and self.config.events:
            self.load_from_calendar(now, self.config.events)

    def block_trading(self, now: datetime) -> bool:
        self.sync(now)
        return any(window.active(now) for window in self._windows)

    def active_window_titles(self, now: datetime) -> List[str]:
        self.sync(now)
        return [window.title for window in self._windows if window.active(now)]
