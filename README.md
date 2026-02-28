# Trading Bot

Personal project to experiment with building and testing automated trading strategies. Add code, tests, and notes here, then commit and push to GitHub.

## Quick start (demo)

Run the dry-run SMC bot against a small synthetic feed that injects sweeps to trigger POIs:

```bash
export PYTHONPATH=src
python -m trading_bot.bot --demo
```

This uses the in-process `PaperBroker`, which immediately fills orders and closes them on stop/TP using the incoming candle high/low. To replay your own day of candles instead of the synthetic generator, add `--candles path/to/file.csv` where the CSV has `timestamp,open,high,low,close,volume(optional)` columns and ISO timestamps.

For MT4 demo routing, wire up the ZeroMQ bridge example:

```bash
export PYTHONPATH=src
python examples/run_mt4_bridge.py \
  --tick-endpoint tcp://127.0.0.1:5555 \
  --command-endpoint tcp://127.0.0.1:5556 \
  --event-endpoint tcp://127.0.0.1:5557
```

The MT4 EA must publish execution events (ACK/REJECT/FILL/CLOSE/SNAPSHOT) back to `--event-endpoint`, and orders sent from Python carry SL/TP so MT4 attaches them at entry. See `docs/mt4_demo_bridge.md` for the EA sketch.

If you want to exercise the bot against a MetaTrader 4 **demo** account instead of the synthetic feed, see `docs/mt4_demo_bridge.md` for a ZeroMQ bridge outline and the runnable adapter in `examples/run_mt4_bridge.py` (connects to an MT4 EA over ZeroMQ).

The bot enforces the current GBP/USD plan:
- London-only trading window (07:00–13:00 London).
- Blocks trading during configured high-impact news windows.
- Fixed 5R targets with no partials or trailing stops.
- Daily stop after 5 consecutive losses.
- Enters every qualifying POI (inducement + swept liquidity) even if multiple trades are open.

## Pipeline (how the bot runs end-to-end)

This project is structured as a **streaming candle processor**: each new 1-minute candle flows through guardrails → strategy → risk sizing → execution → event reconciliation. The same core loop is used in both demo and MT4-bridge mode; only the data source and broker backend change.

### 1) Data ingress (where candles come from)

The bot always consumes a stream of `Candle` objects (`timestamp, open, high, low, close, volume(optional)`):

- **Demo mode (`--demo`)**
  - Candles come from either:
    - a synthetic `SimulatedFeed` (optionally injecting “sweep” spikes to force setups), or
    - a CSV replay via `--candles path/to/file.csv`.
  - This path is useful for dry-runs, replaying a recorded day, and validating logic without any external platform.

- **MT4 demo bridge mode (`examples/run_mt4_bridge.py`)**
  - An MT4 Expert Advisor publishes ticks over ZeroMQ.
  - `MT4ZeroMQClient` receives tick JSON, `MT4Bridge` aggregates ticks into **M1 candles**, and each completed candle is fed into the same bot loop.
  - Execution is routed back to MT4 via ZeroMQ commands, and MT4 publishes execution events back to Python.

### 2) Broker abstraction (how orders get executed)

All execution is done through a small `Broker` interface, so the bot can switch between paper execution and platform routing:

- **`PaperBroker` (demo / in-process)**
  - Immediately "fills" a placed order (paper fill at the requested entry).
  - On each candle, it checks candle high/low against SL/TP and emits a CLOSE event when hit.
  - This is intentionally simple: it is candle-based, does not model spread/slippage/partial fills, and is meant for logic validation.

- **`MT4Broker` (bridge / routed execution)**
  - Converts bot orders into JSON commands (`PLACE`, `CANCEL`, `FLATTEN_ALL`) and sends them to the MT4 EA.
  - Consumes MT4 execution events (`ACK`, `REJECT`, `FILL`, `CLOSE`, `SNAPSHOT`) and converts them into internal `BrokerEvent` objects.
  - This keeps the bot’s internal state aligned with what MT4 reports.

### 3) Event reconciliation (how the bot stays state-consistent)

The bot does not assume execution happened just because it sent an order. Instead it relies on broker events:

- Every candle, the bot drains broker events (FILL/CLOSE/ACK/REJECT).
- On **CLOSE**, the bot:
  - updates realized equity (`PositionSizer.update_equity(pnl)`),
  - updates the daily loss guard (`DailyLossStopper.register_result(pnl)`),
  - logs the close with reason (tp/sl/flatten/cancel).

This means equity and the daily loss counter are driven by **realized outcomes**, not assumptions.

### 4) Pre-trade guardrails (checked before strategy decisions)

Before any setup is evaluated, the bot enforces “must be allowed to trade now” rules:

1. **Daily loss stopper**
   - Tracks consecutive losing trades and halts new entries once the configured limit is hit (default: 5).
   - When halted, the bot flattens all positions and stops placing new orders for that day.

2. **Session filter (London window)**
   - Uses `Europe/London` time and permits entries only during **07:00–13:00 London**.
   - Outside the window, the bot flattens positions and blocks new entries.

3. **News blackout**
   - `NewsFilter` maintains blackout windows (currently config-driven; structured to later sync from a real calendar feed).
   - If a blackout is active, the bot flattens and blocks new entries until the window clears.

If any guardrail is active, the bot exits early for that candle (after flattening and processing resulting broker events).

### 5) Strategy stage (SMC setup detection)

The strategy module (`SMCStrategy`) is a **minimal SMC skeleton** intended to be expanded as rules are refined.

Per candle it:
- Maintains a rolling candle history.
- Updates a lightweight “structure direction” flag (based on taking previous highs/lows).
- Detects a **liquidity sweep** when the current candle:
  - takes prior local highs/lows (2-bar lookback),
  - and closes with rejection (bearish after sweeping up, bullish after sweeping down).
- When a sweep occurs, it registers a POI:
  - selects the POI zone using a wick-vs-body heuristic,
  - flags inducement when recent price action compresses (tight closes),
  - and tries to anchor the POI to the most recent structure direction.
- If the POI qualifies (sweep and/or inducement), it proposes a limit order:
  - **Entry** at the POI edge,
  - **Stop** based on POI width (fallback to a candle-based minimum),
  - **Take profit** fixed at **5R**.

The output of the strategy stage is a list of `ProposedOrder` objects (can be empty or multiple).

### 6) Risk & sizing (turning a setup into position size)

For each proposed order:
- The bot computes **stop distance** (`abs(entry - stop)`).
- `PositionSizer` calculates units so the trade risks a fixed fraction of equity:
  - default: **1% risk per trade**
  - units are derived from `risk_capital / stop_distance`.
- The bot then submits the order to the broker with SL/TP already attached.

### 7) The exact per-candle loop order

For each incoming candle, the bot runs the following sequence:

1. **Broker simulation step (paper only)**: update paper positions using candle high/low (`PaperBroker.on_candle`).
2. **Drain broker events** and update equity + daily loss counter on CLOSE.
3. **Reset daily stopper** if the date has changed.
4. **Run guardrails** (daily stop / session window / news blackout):
   - if blocked → flatten, drain events, and skip strategy for this candle.
5. **Run strategy** (`SMCStrategy.on_candle`) to generate proposed orders.
6. **Size and place** each order via the broker.
7. **Drain any final events** and continue to the next candle.

When the feed ends, the bot performs a final event drain and logs completion.

---

### Notes / current scope

- The default entry point supports **demo mode** (`--demo`) and candle replay; **MT5 live feed is not implemented yet**.
- The MT4 path is designed for **demo-only safety** via a ZeroMQ bridge.
- The paper execution model is intentionally simplified and should be upgraded with spread/slippage and more realistic fill logic when moving beyond dry-run validation.

### Verifying the committed changes locally

To confirm the latest commits are present in your clone:

```bash
git log --oneline -5
```

You should see entries similar to `Clarify demo-only entry point` and `Initial commit`. If you do not, run `git fetch` and ensure you are on the `work` branch.
