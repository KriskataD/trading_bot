# MT4 demo bridge plan

This repository currently supports the synthetic `--demo` run only. To experiment on a MetaTrader 4 **demo** account (no live money), you can bridge MT4 tick data and order routing into the Python bot. The outline below keeps the risk limited to demo and avoids any MT5 dependency.

## What to build
1. **MT4 → Python price feed**: an MQL4 Expert Advisor publishes ticks/candles to a local ZeroMQ socket. The Python side consumes those messages and converts them into `Candle` objects for the bot.
2. **Python → MT4 execution**: when the bot opens/closes positions, a Python bridge sends commands back to MT4 over the same ZeroMQ channel. The EA receives the commands and submits demo orders.
3. **Demo-only safety**: run everything on a MetaTrader 4 demo account to guarantee no live funds are touched.

## MQL4 EA sketch (publisher/router)
Place a simple EA on a chart in your MT4 terminal. It should:
- Open a ZeroMQ `REQ`/`REP` or `PUB`/`SUB` socket to `tcp://127.0.0.1:5555`.
- On every tick, publish the latest tick or aggregated M1 candle.
- Listen for JSON commands to open/close positions and execute them on the demo account.

Example structure (condensed for brevity):
```mq4
#include <zlib.mqh>            // Include your ZeroMQ binding

int OnInit() {
    zmqConnect("tcp://127.0.0.1:5555");
    return(INIT_SUCCEEDED);
}

void OnTick() {
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    string payload = StringFormat(
        "{\"symbol\":\"%s\",\"bid\":%f,\"ask\":%f,\"time\":%d}",
        _Symbol, bid, ask, TimeCurrent()
    );
    zmqPublish(payload);  // Your binding should handle framing

    string command = zmqPollCommand();
    if (command != "") {
        // parse JSON and submit demo orders via OrderSend/OrderClose
    }
}
```
Use any open-source ZeroMQ binding for MQL4 (several are available) and keep lot sizes small (e.g., 0.01) since this is demo-only.

## How to run the Python side (ZeroMQ adapter)
The repository now ships a runnable example that wires the bot to an MT4 EA over ZeroMQ. You need `pyzmq` installed locally:

```bash
pip install pyzmq
```

Then start the adapter from the repo root (it will subscribe to ticks and send order commands back):

```bash
export PYTHONPATH=src
python examples/run_mt4_bridge.py \
  --tick-endpoint tcp://127.0.0.1:5555 \
  --command-endpoint tcp://127.0.0.1:5556
```

What the adapter does:
- Connects to the EA's tick publisher (`--tick-endpoint`), parses each JSON tick with `MT4Bridge.parse_tick`, and aggregates them into M1 candles via `MT4Bridge.on_tick`.
- Feeds each completed candle into the core bot (`TradingBot.process_candle`), so the strategy/risk stack runs exactly as it does in the synthetic `--demo` mode.
- When the bot places an order, it calls `MT4Bridge.build_order_command` and pushes the JSON back to MT4 over `--command-endpoint` for the EA to submit on the demo account.

The adapter code lives in `examples/run_mt4_bridge.py` and uses the helper client `MT4ZeroMQClient` from `src/trading_bot/integrations/mt4_bridge.py`.

## Demo safety checklist
- Use a dedicated MT4 **demo** account; never reuse live credentials.
- Cap lot sizes in the EA and reject any order larger than your chosen demo limit.
- Run the bridge locally (127.0.0.1) to avoid exposing sockets to the internet.
- Dry-run the bridge with a paper symbol (or disabled trading) before enabling live demo execution.

## Next steps to productionize
- Harden the ZeroMQ framing (heartbeats, reconnects, backpressure handling).
- Add signature/nonce checks so only your Python bot can issue commands.
- Enrich the MQL4 side with position reconciliation to keep the bot's state aligned with MT4 fills.
- Write integration tests that replay recorded MT4 ticks through the bridge to validate candles and risk controls.
