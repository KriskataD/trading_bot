from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Protocol


@dataclass
class BrokerEvent:
    type: str  # "ACK"|"REJECT"|"FILL"|"CLOSE"|"SNAPSHOT"
    client_id: str
    ticket: Optional[int]
    time: datetime
    pnl: Optional[float] = None
    reason: Optional[str] = None
    payload: Optional[Dict] = None


class Broker(Protocol):
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
        ...

    def cancel(self, client_id: str) -> None:
        ...

    def flatten_all(self, reason: str) -> None:
        ...

    def drain_events(self) -> List[BrokerEvent]:
        ...
