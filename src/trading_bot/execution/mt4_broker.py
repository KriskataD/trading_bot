from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from trading_bot.execution.broker import Broker, BrokerEvent
from trading_bot.integrations.mt4_bridge import MT4ZeroMQClient


class MT4Broker(Broker):
    def __init__(self, client: MT4ZeroMQClient, symbol: str) -> None:
        self.client = client
        self.symbol = symbol

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
        command = {
            "type": "PLACE",
            "client_id": client_id,
            "symbol": symbol or self.symbol,
            "side": side,
            "order_type": order_type,
            "entry": entry,
            "sl": stop,
            "tp": take_profit,
            "units": units,
        }
        self.client.send_command(command)

    def cancel(self, client_id: str) -> None:
        self.client.send_command({"type": "CANCEL", "client_id": client_id})

    def flatten_all(self, reason: str) -> None:
        self.client.send_command({"type": "FLATTEN_ALL", "reason": reason})

    def _convert_event(self, message: Dict) -> BrokerEvent:
        raw_time = message.get("time")
        dt = (
            datetime.fromtimestamp(raw_time, tz=timezone.utc)
            if raw_time is not None
            else datetime.now(tz=timezone.utc)
        )
        payload_keys = {"type", "client_id", "ticket", "time", "pnl", "reason"}
        payload: Optional[Dict] = {
            k: v for k, v in message.items() if k not in payload_keys
        }
        if not payload:
            payload = None

        return BrokerEvent(
            type=message.get("type", "SNAPSHOT"),
            client_id=str(message.get("client_id", "")),
            ticket=message.get("ticket"),
            time=dt,
            pnl=message.get("pnl"),
            reason=message.get("reason"),
            payload=payload,
        )

    def drain_events(self) -> List[BrokerEvent]:
        events: List[BrokerEvent] = []
        for message in self.client.drain_event_messages():
            events.append(self._convert_event(message))
        return events
