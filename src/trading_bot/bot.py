from __future__ import annotations

import argparse
import logging
from datetime import datetime

from typing import Callable, Optional

from trading_bot.config import DEFAULT_CONFIG, TradingBotConfig
from trading_bot.data.market_data import Candle, SimulatedFeed
from trading_bot.execution.executor import ExecutionEngine, Position
from trading_bot.features.news import NewsFilter
from trading_bot.features.session import SessionFilter
from trading_bot.risk.controls import DailyLossStopper, PositionSizer
from trading_bot.strategy.smc import ProposedOrder, SMCStrategy


def build_logger(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


class TradingBot:
    def __init__(
        self,
        config: TradingBotConfig,
        order_hook: Optional[Callable[[Position, str], None]] = None,
    ):
        self.config = config
        self.strategy = SMCStrategy()
        self.session_filter = SessionFilter(config.session)
        self.news_filter = NewsFilter(config.news)
        self.execution = ExecutionEngine()
        self.sizer = PositionSizer(equity=10_000.0, config=config.risk)
        self.stopper = DailyLossStopper(config.risk)
        self.logger = logging.getLogger(__name__)
        self.order_hook = order_hook

    def handle_closed_positions(self, closed_positions) -> None:
        for pos in closed_positions:
            pnl = pos.pnl or 0.0
            self.sizer.update_equity(pnl)
            self.stopper.register_result(pnl)
            self.logger.info(
                "Closed %s #%s from POI %s | pnl=%.2f | equity=%.2f",
                pos.direction,
                pos.id,
                pos.poi_id,
                pnl,
                self.sizer.equity,
            )
            if self.order_hook:
                self.order_hook(pos, "close")

    def place_orders(self, orders: list[ProposedOrder], now: datetime) -> None:
        for order in orders:
            stop_distance = abs(order.stop - order.entry)
            sizing = self.sizer.size_order(stop_distance)
            position = self.execution.place_order(
                direction=order.direction,
                entry=order.entry,
                stop=order.stop,
                take_profit=order.take_profit,
                units=sizing.units,
                poi_id=order.poi.id,
                opened_at=now,
            )
            self.logger.info(
                "Placed %s #%s at %.5f | stop %.5f | tp %.5f | units %.2f | poi %s",
                order.direction,
                position.id,
                order.entry,
                order.stop,
                order.take_profit,
                sizing.units,
                order.poi.id,
            )
            if self.order_hook:
                self.order_hook(position, "open")

    def flatten_if_blocked(self, now: datetime) -> bool:
        if self.stopper.halted(now):
            self.logger.warning("Daily loss limit reached; halting new entries and flattening.")
            self.execution.flatten_all(now)
            return True
        if not self.session_filter.in_session(now):
            self.logger.info("Outside London window; flattening positions.")
            self.execution.flatten_all(now)
            return True
        if self.news_filter.block_trading(now):
            active_titles = ", ".join(self.news_filter.active_window_titles(now))
            self.logger.info("News blackout active (%s); flattening positions.", active_titles)
            self.execution.flatten_all(now)
            return True
        return False

    def process_candle(self, candle: Candle) -> None:
        now = candle.timestamp
        self.stopper.reset_if_new_session(now)
        if self.flatten_if_blocked(now):
            return

        closed = self.execution.on_price(candle)
        self.handle_closed_positions(closed)

        orders = self.strategy.on_candle(candle)
        if orders:
            self.place_orders(orders, now)

    def run(self, feed) -> None:
        for candle in feed.stream():
            self.process_candle(candle)

        self.logger.info(
            "Session complete | trades taken: %s | open positions: %s",
            len(self.execution.trades),
            len(self.execution.open_positions()),
        )


def build_demo_feed() -> SimulatedFeed:
    start = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    feed = SimulatedFeed.constant_move(start=start, start_price=1.2700, bars=120, direction=0.0002)
    # Inject a few sweeps by modifying some candles to trigger POIs
    candles = list(feed.stream())
    if len(candles) > 20:
        spike = candles[15]
        candles[15] = Candle(
            timestamp=spike.timestamp,
            open=spike.open,
            high=spike.high + 0.0015,
            low=spike.low,
            close=spike.open - 0.0007,
        )
    if len(candles) > 40:
        dump = candles[35]
        candles[35] = Candle(
            timestamp=dump.timestamp,
            open=dump.open,
            high=dump.high,
            low=dump.low - 0.0012,
            close=dump.open + 0.0006,
        )
    return SimulatedFeed(candles)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GBP/USD SMC trading bot")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run a simulated dry-run with synthetic sweeps",
    )
    args = parser.parse_args()

    build_logger(DEFAULT_CONFIG.log_level)
    bot = TradingBot(DEFAULT_CONFIG)
    if args.demo:
        feed = build_demo_feed()
    else:
        raise NotImplementedError(
            "Live MT5 feed not implemented yet; run with --demo while wiring the broker"
        )
    bot.run(feed)


if __name__ == "__main__":
    main()
