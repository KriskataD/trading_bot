from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from trading_bot.data.market_data import Candle
from trading_bot.execution.broker import Broker, BrokerEvent


@dataclass
class PaperPosition:
    ticket: int
    client_id: str
    side: str  # "buy" or "sell"
    entry: float
    stop: float
    take_profit: float
    units: float
    opened_at: datetime
    closed_at: Optional[datetime] = None
    pnl: Optional[float] = None

    def active(self) -> bool:
        return self.closed_at is None

    def check_outcome(self, candle: Candle) -> Optional[tuple[float, str]]:
        if not self.active():
            return None

        # Stops/TPs are evaluated against the full candle range to mimic intra-bar fills.
        if self.side == "buy":
            if candle.low <= self.stop:
                return (self.stop - self.entry) * self.units, "sl"
            if candle.high >= self.take_profit:
                return (self.take_profit - self.entry) * self.units, "tp"
        else:
            if candle.high >= self.stop:
                return (self.entry - self.stop) * self.units, "sl"
            if candle.low <= self.take_profit:
                return (self.entry - self.take_profit) * self.units, "tp"
        return None


class PaperBroker(Broker):
    def __init__(self) -> None:
        self._positions: Dict[str, PaperPosition] = {}
        self._next_ticket = 1
        self._events: List[BrokerEvent] = []

    def place_order(
        self,
        client_id: str,
        symbol: str,
        side: str,
        order_type: str,
        entry: float,
        stop: float,
        take_profit: float,
        units: float,
    ) -> None:
        # Immediate fill at entry for paper mode.
        position = PaperPosition(
            ticket=self._next_ticket,
            client_id=client_id,
            side=side,
            entry=entry,
            stop=stop,
            take_profit=take_profit,
            units=units,
            opened_at=datetime.utcnow(),
        )
        self._positions[client_id] = position
        self._next_ticket += 1
        self._events.append(
            BrokerEvent(
                type="FILL",
                client_id=client_id,
                ticket=position.ticket,
                time=position.opened_at,
                payload={"entry": entry, "side": side, "units": units},
            )
        )

    def cancel(self, client_id: str) -> None:
        position = self._positions.pop(client_id, None)
        if not position or not position.active():
            return
        now = datetime.utcnow()
        position.closed_at = now
        position.pnl = 0.0
        self._events.append(
            BrokerEvent(
                type="CLOSE",
                client_id=client_id,
                ticket=position.ticket,
                time=now,
                pnl=0.0,
                reason="cancel",
            )
        )

    def flatten_all(self, reason: str) -> None:
        now = datetime.utcnow()
        for client_id, position in list(self._positions.items()):
            if not position.active():
                continue
            position.closed_at = now
            position.pnl = 0.0
            self._events.append(
                BrokerEvent(
                    type="CLOSE",
                    client_id=client_id,
                    ticket=position.ticket,
                    time=now,
                    pnl=0.0,
                    reason=reason,
                )
            )
            del self._positions[client_id]

    def on_candle(self, candle: Candle) -> None:
        for client_id, position in list(self._positions.items()):
            outcome = position.check_outcome(candle)
            if outcome is None:
                continue
            pnl, reason = outcome
            position.closed_at = candle.timestamp
            position.pnl = pnl
            self._events.append(
                BrokerEvent(
                    type="CLOSE",
                    client_id=client_id,
                    ticket=position.ticket,
                    time=candle.timestamp,
                    pnl=pnl,
                    reason=reason,
                )
            )
            del self._positions[client_id]

    def drain_events(self) -> List[BrokerEvent]:
        events = list(self._events)
        self._events.clear()
        return events
