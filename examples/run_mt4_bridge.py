from __future__ import annotations

import argparse

from trading_bot.bot import TradingBot, build_logger
from trading_bot.config import DEFAULT_CONFIG
from trading_bot.execution.mt4_broker import MT4Broker
from trading_bot.integrations.mt4_bridge import MT4ZeroMQClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bot against MT4 via ZeroMQ")
    parser.add_argument(
        "--tick-endpoint",
        default="tcp://127.0.0.1:5555",
        help="ZeroMQ endpoint where the MT4 EA publishes ticks",
    )
    parser.add_argument(
        "--command-endpoint",
        default="tcp://127.0.0.1:5556",
        help="ZeroMQ endpoint where order commands are pushed back to MT4",
    )
    parser.add_argument(
        "--event-endpoint",
        default="tcp://127.0.0.1:5557",
        help="ZeroMQ endpoint where execution events are published by MT4",
    )
    args = parser.parse_args()

    build_logger(DEFAULT_CONFIG.log_level)

    with MT4ZeroMQClient(
        tick_endpoint=args.tick_endpoint,
        command_endpoint=args.command_endpoint,
        event_endpoint=args.event_endpoint,
    ) as client:
        broker = MT4Broker(client, DEFAULT_CONFIG.instrument.symbol)
        bot = TradingBot(DEFAULT_CONFIG, broker=broker)
        try:
            for candle in client.stream_candles():
                bot.handle_broker_events()
                bot.process_candle(candle)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
