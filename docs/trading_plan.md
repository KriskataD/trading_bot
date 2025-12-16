# GBP/USD 1-Minute Live Trading Strategy Blueprint

This document captures the current constraints and proposed architecture for the GBP/USD live strategy using Smart Money Concepts (SMC) without traditional indicators.

## Trading Rules & Risk Parameters
- **Market & Venue:** Forex GBP/USD via Blueberry Markets on MetaTrader.
- **Timeframe:** Only M1 bars for execution and monitoring.
- **Session Filter:** Trade **London session only**, specifically **07:00–13:00 London time**. Disable order placement outside this window and avoid holding positions beyond the session end.
- **Risk/Reward:** Each position targets **5R** (risk multiples), enforced through take-profit and stop-loss sizing. No partial profits or trailing stops—single TP/SL per trade.
- **Daily Risk Limit:** Halt trading after **5 consecutive losing trades** in a day; reset at session roll.
- **Position Sizing:** Per-trade risk fixed as a percentage of account equity (configurable); lot size computed from stop distance.
- **Entry Frequency:** Execute **every qualified POI setup** (per the inducement/sweep rules) even if other trades are already open, so long as the session/news and daily loss guardrails permit.
- **Order Types:** Primarily limit orders placed at SMC-derived levels, with market orders as contingency if price sweeps the level and criteria remain valid.
- **News Filter:** No trading during **high-impact expected news** (Forex Factory feed). Flat the book heading into the blackout window and keep the system out of trades until the news window clears.

## Strategy Description (SMC with Light Deviations)
Describe new variations inline when you have them; the structure below shows where to plug details.

1. **Market Structure Mapping**
   - Identify current swing high/low on M1 with higher-timeframe context from M5/M15 for bias (directional context only; still execute on M1).
   - Track **break of structure (BOS)** and **change of character (CHOCH)** events; store last confirmed structure point.
2. **Liquidity & Fair Value Zones**
   - Mark equal highs/lows, session highs/lows, and Asian range as liquidity pools.
   - Compute imbalances/fair value gaps (FVG) on M1; score them by recency and size.
3. **Premium/Discount & Point of Interest (POI)**
   - Use recent swing range to determine premium/discount. Favor longs in discount, shorts in premium.
   - **Supply/Demand Zone Selection:** Define the zone by the candle body unless the wick is larger than the body, in which case the wick defines the zone. Treat the zone as a valid POI only when paired with **inducement** and/or **swept liquidity** (see definitions below).
   - Select POIs where liquidity + FVG + structure align. Document entry refinement rules (e.g., refined order block or FVG tap).
4. **Entry Triggers**
   - Wait for price to sweep a liquidity pool near the POI, then confirm intent via a lower-timeframe CHOCH on M1.
   - Place limit order at refined POI with stop at invalidation (e.g., below/above OB/FVG boundary) targeting 5R.
5. **Risk Controls & Invalidation**
   - Cancel pending orders if structure flips against the setup before fill.
   - No averaging down/up within the same POI; multiple **distinct POIs can be traded in parallel** if they each qualify.
   - No partials or trailing stops; keep the fixed 5R exit.

## Data & Feature Pipeline
- **Market Data:** Stream M1 candles and tick quotes from MetaTrader 5 API (or bridge) for live trading; collect historical M1 data for backtests.
- **Feature Extraction:**
  - Real-time derivation of structure points, BOS/CHOCH, liquidity pools, and FVGs from the M1 stream.
  - Session markers (Sydney/London/New York) for contextual filters, with the **07:00–13:00 London** trading window enforced.
  - Economic calendar pull (Forex Factory or equivalent) to tag **high-impact news windows** and block trading/flatten positions during those intervals.
- **Storage:** Append ticks/candles to local database (e.g., SQLite/Parquet) for audit and replay. Persist derived events (BOS, CHOCH, FVG) for offline analysis.

## Backtesting & Simulation Plan
- **Historical M1 replay** with tick-level interpolation for fill modeling.
- **Execution Model:** Include spread, commissions, and slippage assumptions matching Blueberry/MT5. Simulate partial fills on limit orders when price touches POI.
- **Metrics:** Win rate, average R, max consecutive losses, daily drawdown, expectancy, Sharpe/Sortino, and latency-to-fill distribution.
- **Walk-forward validation** across sessions (London vs. New York) to test robustness, with primary focus on London-only performance.

## System Architecture
- **Modules:**
  - `data`: MT5 data connector (live + historical download), stream normalizer, persistence.
  - `features`: structure detection (swing points, BOS/CHOCH), liquidity pool detection, FVG detection, session calendar.
  - `strategy`: bias determination, POI selection, entry trigger, order sizing to 5R.
  - `risk`: per-trade risk calc, daily loss stopper (max 5 consecutive losses), kill switch, spread/slippage guards.
  - `execution`: MT5 order router with retry/backoff, order tracking, reconciliation with broker fills.
  - `monitoring`: structured logging, metrics, alerting (e.g., webhook/Slack), dashboards for PnL and exposure.
- **Configuration:** `.env` (broker creds), YAML/JSON strategy settings (risk %, session filters, slippage cap).

## Operational Workflow
1. **Pre-session checks:** Connectivity to MT5, account balance, symbol settings (spread/commission), time sync.
2. **Live loop:**
   - Stream ticks/M1 candles → update features → evaluate strategy → issue/cancel orders → log actions.
   - Enforce London-only trading window; pause entries outside **07:00–13:00 London**.
   - Enforce daily loss stopper after 5 consecutive losses.
   - Evaluate **all simultaneous qualifying POIs** and place orders for each, subject to session/news/daily-stop constraints.
   - Apply **high-impact news guard**: block new entries and flatten any open positions before the blackout window begins; resume only after the window ends.
3. **Post-session:** Persist logs, generate PnL and compliance report, archive tick/candle data.

## Key SMC Definitions for Alignment
- **Inducement:** A deliberate-looking price move that entices traders to enter in the direction you intend to fade, typically creating nearby resting liquidity (e.g., equal highs/lows or a minor pullback just **ahead** of your POI in the path of price). The inducement should sit between current price and the POI so that when price approaches the zone, that resting liquidity is consumed first, fueling the reaction at the POI.
- **Swept Liquidity (Liquidity Grab):** A sharp probe through a known liquidity pool (previous swing high/low, equal highs/lows, session high/low) that takes out resting stops, then shows rejection. The sweep is most meaningful when it clears liquidity **before** your POI and leaves the POI intact (i.e., the zone itself has not been invalidated by a structure break). For POI qualification, prefer sweeps that **draw from a zone that already caused a structure break**—i.e., the liquidity pool formed after a BOS/CHOCH from that zone is now cleared while the original zone stays respected. This ties the sweep to demonstrated intent and keeps the POI anchored to the structure-breaking origin.

## Next Inputs Needed
- Detailed SMC deviations (how to refine POIs, exact CHOCH/BOS definitions, stop placement rules).
- Session filters (news windows) and exact London session hours/timezone alignment. **Currently: 07:00–13:00 London; no trading during high-impact news (Forex Factory), and be flat during those windows.**
- Preferred slippage/spread thresholds and minimum RR enforcement.
- Any additional management rules while keeping single-entry, single-exit at 5R.
