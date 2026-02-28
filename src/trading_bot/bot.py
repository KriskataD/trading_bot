from __future__ import annotations

import argparse
import logging
from datetime import datetime

from trading_bot.config import DEFAULT_CONFIG, TradingBotConfig
from trading_bot.data.market_data import Candle, SimulatedFeed, load_candles_csv
from trading_bot.execution.broker import Broker
from trading_bot.execution.paper_broker import PaperBroker
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
        broker: Broker,
    ):
        self.config = config
        self.strategy = SMCStrategy()
        self.session_filter = SessionFilter(config.session)
        self.news_filter = NewsFilter(config.news)
        self.sizer = PositionSizer(equity=10_000.0, config=config.risk)
        self.stopper = DailyLossStopper(config.risk)
        self.logger = logging.getLogger(__name__)
        self.broker = broker

    def handle_broker_events(self) -> None:
        # Pull and reconcile any broker-side state changes before acting on new signals.
        for event in self.broker.drain_events():
            if event.type == "CLOSE":
                pnl = event.pnl or 0.0
                self.sizer.update_equity(pnl)
                self.stopper.register_result(pnl)
                self.logger.info(
                    "Closed client_id=%s ticket=%s pnl=%.2f reason=%s equity=%.2f",
                    event.client_id,
                    event.ticket,
                    pnl,
                    event.reason or "",
                    self.sizer.equity,
                )
            elif event.type == "REJECT":
                self.logger.warning(
                    "Order rejected client_id=%s reason=%s",
                    event.client_id,
                    event.reason or "",
                )
            elif event.type == "ACK":
                self.logger.info("Order ack client_id=%s ticket=%s", event.client_id, event.ticket)
            elif event.type == "FILL":
                self.logger.info(
                    "Order fill client_id=%s ticket=%s",
                    event.client_id,
                    event.ticket,
                )

    def place_orders(self, orders: list[ProposedOrder], now: datetime) -> None:
        for order in orders:
            # Position size derives strictly from stop distance to keep 1% risk per trade.
            stop_distance = abs(order.stop - order.entry)
            sizing = self.sizer.size_order(stop_distance)
            client_id = f"{order.poi.id}:{now.isoformat()}"
            side = "buy" if order.direction == "long" else "sell"
            self.broker.place_order(
                client_id=client_id,
                symbol=self.config.instrument.symbol,
                side=side,
                order_type="limit",
                entry=order.entry,
                stop=order.stop,
                take_profit=order.take_profit,
                units=sizing.units,
            )
            self.logger.info(
                "Placed %s client_id=%s at %.5f | stop %.5f | tp %.5f | units %.2f | poi %s",
                order.direction,
                client_id,
                order.entry,
                order.stop,
                order.take_profit,
                sizing.units,
                order.poi.id,
            )

    def flatten_if_blocked(self, now: datetime) -> bool:
        # Guardrails that override strategy signals and force a flat book.
        if self.stopper.halted(now):
            self.logger.warning("Daily loss limit reached; halting new entries and flattening.")
            self.broker.flatten_all("daily_stop")
            return True
        if not self.session_filter.in_session(now):
            self.logger.info("Outside London window; flattening positions.")
            self.broker.flatten_all("session_block")
            return True
        if self.news_filter.block_trading(now):
            active_titles = ", ".join(self.news_filter.active_window_titles(now))
            self.logger.info("News blackout active (%s); flattening positions.", active_titles)
            self.broker.flatten_all("news_block")
            return True
        return False

    def process_candle(self, candle: Candle) -> None:
        now = candle.timestamp
        if isinstance(self.broker, PaperBroker):
            self.broker.on_candle(candle)

        # Always reconcile broker updates and guardrails before pushing fresh orders.
        self.handle_broker_events()
        self.stopper.reset_if_new_session(now)
        if self.flatten_if_blocked(now):
            self.handle_broker_events()
            return

        orders = self.strategy.on_candle(candle)
        if orders:
            self.place_orders(orders, now)

    def run(self, feed) -> None:
        for candle in feed.stream():
            self.process_candle(candle)
        # Flush any remaining events (e.g., flatten requests).
        self.handle_broker_events()

        self.logger.info("Session complete")


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
    parser.add_argument(
        "--candles",
        help="CSV file with candles for demo mode; columns: timestamp,open,high,low,close,volume(optional)",
    )
    args = parser.parse_args()

    build_logger(DEFAULT_CONFIG.log_level)
    if args.demo:
        feed = build_demo_feed() if not args.candles else SimulatedFeed(load_candles_csv(args.candles))
        broker: Broker = PaperBroker()
        bot = TradingBot(DEFAULT_CONFIG, broker=broker)
    else:
        raise NotImplementedError(
            "Live MT5 feed not implemented yet; run with --demo while wiring the broker"
        )
    bot.run(feed)


if __name__ == "__main__":
    main()
