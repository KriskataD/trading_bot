from __future__ import annotations

import argparse

from trading_bot.bot import DEFAULT_CONFIG, TradingBot, build_logger
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
    args = parser.parse_args()

    build_logger(DEFAULT_CONFIG.log_level)
    bot = TradingBot(DEFAULT_CONFIG)

    with MT4ZeroMQClient(
        tick_endpoint=args.tick_endpoint,
        command_endpoint=args.command_endpoint,
    ) as client:
        bot.order_hook = client.send_order
        try:
            for candle in client.stream_candles():
                bot.process_candle(candle)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
