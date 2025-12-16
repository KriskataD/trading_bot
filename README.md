# Trading Bot

Personal project to experiment with building and testing automated trading strategies. Add code, tests, and notes here, then commit and push to GitHub.

## Quick start (demo)

Run the dry-run SMC bot against a small synthetic feed that injects sweeps to trigger POIs:

```bash
export PYTHONPATH=src
python -m trading_bot.bot --demo
```

Live MT5 routing is not wired yet; the current entry point only supports the `--demo` feed until broker connectivity is added.

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
