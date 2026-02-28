from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Generator, Iterable, List, Optional


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body_high(self) -> float:
        return max(self.open, self.close)

    @property
    def body_low(self) -> float:
        return min(self.open, self.close)

    @property
    def wick_top(self) -> float:
        return self.high

    @property
    def wick_bottom(self) -> float:
        return self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def wick_top_size(self) -> float:
        return self.high - self.body_high

    @property
    def wick_bottom_size(self) -> float:
        return self.body_low - self.low


class SimulatedFeed:
    """Simple generator-based feed for backtests or dry-runs."""

    def __init__(self, candles: Iterable[Candle]):
        self._candles = list(candles)

    def stream(self) -> Generator[Candle, None, None]:
        for candle in self._candles:
            yield candle

    @staticmethod
    def constant_move(
        start: datetime,
        start_price: float,
        bars: int,
        direction: float = 0.0005,
    ) -> "SimulatedFeed":
        """Create a feed that drifts by a fixed increment each bar."""

        candles: List[Candle] = []
        last_close = start_price
        for i in range(bars):
            open_price = last_close
            high = open_price + abs(direction)
            low = open_price - abs(direction)
            close = open_price + direction
            candles.append(
                Candle(
                    timestamp=start + timedelta(minutes=i),
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=0.0,
                )
            )
            last_close = close
        return SimulatedFeed(candles)


def load_candles_csv(path: str) -> List[Candle]:
    candles: List[Candle] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_raw = row["timestamp"]
            ts_clean = ts_raw.replace("Z", "+00:00")
            ts = datetime.fromisoformat(ts_clean)
            candles.append(
                Candle(
                    timestamp=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                )
            )
    return candles
