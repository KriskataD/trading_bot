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

## Pipeline (how the loop runs)

1) **Data ingress**  
   - Demo mode pulls candles from a synthetic `SimulatedFeed` or a CSV (`timestamp,open,high,low,close,volume`).  
   - Live MT4 demo would replace the feed with the `MT4ZeroMQClient` stream (ticks aggregated to 1m candles by `MT4Bridge`).

2) **Pre-trade guardrails** (always run before any strategy check)  
   - `NewsFilter` loads blackout windows from config and blocks entries/forces flattening when active.  
   - `SessionFilter` keeps trading inside 07:00–13:00 London; outside that window the broker is flattened.  
   - `DailyLossStopper` resets each session and halts new orders after 5 straight losses.

3) **Strategy detection (SMC)**  
   - `SMCStrategy` tracks a rolling candle history, updating the last break-of-structure direction.  
   - A sweep is spotted when the current candle takes the prior two-bar high/low and closes in rejection; that anchors a POI to the BOS direction.  
   - A POI stores zone bounds (wick/body dependent), flags inducement proximity, and is considered tradable if it carries the sweep or inducement.  
   - Limit entry sits at the POI edge, stop at zone width (or half-candle fallback), and TP at 5R (from `RiskConfig.reward_r_multiple`).

4) **Risk and sizing**  
   - `PositionSizer` sizes units from equity and stop distance to risk 1% per trade (`risk_per_trade`).  
   - Equity is updated only when broker CLOSE events arrive (marks realized PnL).

5) **Execution & reconciliation**  
   - Demo mode routes orders to `PaperBroker`, which fills instantly at the requested entry and resolves SL/TP against incoming candles.  
   - The broker produces events (`FILL`, `CLOSE`, `ACK/REJECT`), which the bot drains every candle before/after decisions to keep state consistent.  
   - A live MT4 adapter would swap in a broker implementation that forwards orders to MetaTrader and relays events back.

6) **Loop order**  
   - For each candle: push it into the broker (paper fill simulation) → drain broker events → reset daily stopper if new date → apply guardrails (flatten if needed) → run strategy → size/place any proposed orders → drain final events → repeat.  
   - When the feed ends, a final drain flushes remaining events and logs “Session complete.”

### Verifying the committed changes locally

To confirm the latest commits are present in your clone:

```bash
git log --oneline -5
```

You should see entries similar to `Clarify demo-only entry point` and `Initial commit`. If you do not, run `git fetch` and ensure you are on the `work` branch.
