from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time, timedelta
from typing import List, Optional


@dataclass
class SessionConfig:
    """Time-filter configuration for the London session window."""

    start: time = time(hour=7)  # 07:00 London
    end: time = time(hour=13)  # 13:00 London
    timezone: str = "Europe/London"


@dataclass
class RiskConfig:
    """Risk parameters enforced by the bot."""

    risk_per_trade: float = 0.01  # 1% of equity
    max_consecutive_losses: int = 5
    reward_r_multiple: float = 5.0
    spread_slippage_buffer: float = 0.00015  # 1.5 pips buffer on GBP/USD


@dataclass
class InstrumentConfig:
    symbol: str = "GBPUSD"
    timeframe_minutes: int = 1


@dataclass
class NewsEvent:
    title: str
    start_offset: timedelta
    end_offset: timedelta


@dataclass
class NewsConfig:
    """High-impact news guardrails."""

    blackout_minutes_before: int = 15
    blackout_minutes_after: int = 15
    events: List[NewsEvent] = field(default_factory=list)


@dataclass
class StorageConfig:
    data_path: str = "./data"


@dataclass
class TradingBotConfig:
    session: SessionConfig = field(default_factory=SessionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    instrument: InstrumentConfig = field(default_factory=InstrumentConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    dry_run: bool = True
    log_level: str = "INFO"


DEFAULT_CONFIG = TradingBotConfig()
