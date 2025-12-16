from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from trading_bot.data.market_data import Candle
from trading_bot.execution.executor import Position


@dataclass(frozen=True)
class MT4Tick:
    symbol: str
    bid: float
    ask: float
    time: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


class MT4Bridge:
    """Minimal adapter shape for a ZeroMQ-based MT4 demo bridge."""

    def __init__(self, symbol: str = "GBPUSD"):
        self.symbol = symbol
        self._current_minute: Optional[datetime] = None
        self._open: Optional[float] = None
        self._high: Optional[float] = None
        self._low: Optional[float] = None
        self._close: Optional[float] = None

    def parse_tick(self, payload: str) -> MT4Tick:
        """Parse a JSON payload from the MQL4 EA into an MT4Tick."""

        data = json.loads(payload)
        epoch_seconds = float(data["time"])
        ts = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        return MT4Tick(
            symbol=data["symbol"],
            bid=float(data["bid"]),
            ask=float(data["ask"]),
            time=ts,
        )

    def on_tick(self, tick: MT4Tick) -> Optional[Candle]:
        """Aggregate MT4 ticks into minute candles for the bot."""

        minute = tick.time.replace(second=0, microsecond=0)
        price = tick.mid

        if self._current_minute is None:
            self._start_new_candle(minute, price)
            return None

        if minute == self._current_minute:
            self._high = price if self._high is None else max(self._high, price)
            self._low = price if self._low is None else min(self._low, price)
            self._close = price
            return None

        finished = self._build_candle()
        self._start_new_candle(minute, price)
        return finished

    def build_order_command(self, position: Position, action: str = "open") -> dict:
        """Shape a JSON-serializable command for the MT4 EA."""

        return {
            "action": action,
            "id": position.id,
            "symbol": self.symbol,
            "direction": position.direction,
            "entry": position.entry,
            "stop": position.stop,
            "take_profit": position.take_profit,
            "units": position.units,
            "opened_at": position.opened_at.isoformat(),
        }


class MT4ZeroMQClient:
    """ZeroMQ helper to consume MT4 ticks and forward orders."""

    def __init__(
        self,
        tick_endpoint: str = "tcp://127.0.0.1:5555",
        command_endpoint: str = "tcp://127.0.0.1:5556",
        bridge: Optional[MT4Bridge] = None,
    ) -> None:
        self.tick_endpoint = tick_endpoint
        self.command_endpoint = command_endpoint
        self.bridge = bridge or MT4Bridge()

        self._ctx = None
        self._tick_socket = None
        self._command_socket = None

    def __enter__(self) -> "MT4ZeroMQClient":
        import zmq

        self._ctx = zmq.Context.instance()
        self._tick_socket = self._ctx.socket(zmq.SUB)
        self._tick_socket.connect(self.tick_endpoint)
        self._tick_socket.subscribe("")

        self._command_socket = self._ctx.socket(zmq.PUSH)
        self._command_socket.connect(self.command_endpoint)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._tick_socket:
            self._tick_socket.close(0)
        if self._command_socket:
            self._command_socket.close(0)
        self._tick_socket = None
        self._command_socket = None

    def stream_candles(self):
        if self._tick_socket is None:
            raise RuntimeError("Call `with MT4ZeroMQClient(...)` before streaming.")

        while True:
            payload = self._tick_socket.recv_string()
            tick = self.bridge.parse_tick(payload)
            candle = self.bridge.on_tick(tick)
            if candle:
                yield candle

    def send_order(self, position: Position, action: str = "open") -> None:
        if self._command_socket is None:
            raise RuntimeError("Call `with MT4ZeroMQClient(...)` before sending commands.")

        command = self.bridge.build_order_command(position, action)
        self._command_socket.send_json(command)

    def _start_new_candle(self, minute: datetime, price: float) -> None:
        self._current_minute = minute
        self._open = price
        self._high = price
        self._low = price
        self._close = price

    def _build_candle(self) -> Optional[Candle]:
        if self._current_minute is None:
            return None
        assert self._open is not None and self._high is not None
        assert self._low is not None and self._close is not None

        return Candle(
            timestamp=self._current_minute,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=0.0,
        )
