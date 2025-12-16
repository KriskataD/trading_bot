from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from trading_bot.config import RiskConfig


@dataclass
class OrderSizing:
    units: float
    stop_distance: float
    take_profit_distance: float


class PositionSizer:
    def __init__(self, equity: float, config: RiskConfig):
        self.equity = equity
        self.config = config

    def size_order(self, stop_distance: float) -> OrderSizing:
        risk_capital = self.equity * self.config.risk_per_trade
        units = risk_capital / max(stop_distance, 1e-6)
        return OrderSizing(
            units=units,
            stop_distance=stop_distance,
            take_profit_distance=stop_distance * self.config.reward_r_multiple,
        )

    def update_equity(self, pnl: float) -> None:
        self.equity += pnl


class DailyLossStopper:
    def __init__(self, config: RiskConfig):
        self.config = config
        self.consecutive_losses = 0
        self.last_reset_date: Optional[datetime.date] = None

    def reset_if_new_session(self, now: datetime) -> None:
        current_date = now.date()
        if self.last_reset_date != current_date:
            self.consecutive_losses = 0
            self.last_reset_date = current_date

    def register_result(self, pnl: float) -> None:
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def halted(self, now: datetime) -> bool:
        self.reset_if_new_session(now)
        return self.consecutive_losses >= self.config.max_consecutive_losses
