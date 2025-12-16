from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from trading_bot.data.market_data import Candle


@dataclass
class Position:
    id: int
    direction: str
    entry: float
    stop: float
    take_profit: float
    units: float
    poi_id: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    pnl: Optional[float] = None

    def active(self) -> bool:
        return self.closed_at is None

    def check_outcome(self, candle: Candle) -> Optional[float]:
        if not self.active():
            return None
        if self.direction == "long":
            if candle.low <= self.stop:
                return (self.stop - self.entry) * self.units
            if candle.high >= self.take_profit:
                return (self.take_profit - self.entry) * self.units
        if self.direction == "short":
            if candle.high >= self.stop:
                return (self.entry - self.stop) * self.units
            if candle.low <= self.take_profit:
                return (self.entry - self.take_profit) * self.units
        return None


class ExecutionEngine:
    def __init__(self):
        self._positions: Dict[int, Position] = {}
        self._next_id = 1
        self.trades: List[Position] = []

    def place_order(
        self,
        direction: str,
        entry: float,
        stop: float,
        take_profit: float,
        units: float,
        poi_id: str,
        opened_at: datetime,
    ) -> Position:
        position = Position(
            id=self._next_id,
            direction=direction,
            entry=entry,
            stop=stop,
            take_profit=take_profit,
            units=units,
            poi_id=poi_id,
            opened_at=opened_at,
        )
        self._positions[self._next_id] = position
        self.trades.append(position)
        self._next_id += 1
        return position

    def flatten_all(self, now: datetime) -> None:
        for position in list(self._positions.values()):
            if position.active():
                position.closed_at = now
                position.pnl = 0.0
                del self._positions[position.id]

    def on_price(self, candle: Candle) -> List[Position]:
        closed: List[Position] = []
        for position in list(self._positions.values()):
            result = position.check_outcome(candle)
            if result is not None:
                position.closed_at = candle.timestamp
                position.pnl = result
                closed.append(position)
                del self._positions[position.id]
        return closed

    def open_positions(self) -> List[Position]:
        return list(self._positions.values())
