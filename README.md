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

### Verifying the committed changes locally

To confirm the latest commits are present in your clone:

```bash
git log --oneline -5
```

You should see entries similar to `Clarify demo-only entry point` and `Initial commit`. If you do not, run `git fetch` and ensure you are on the `work` branch.
