from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from trading_bot.data.market_data import Candle


@dataclass
class POI:
    id: str
    direction: str
    zone_low: float
    zone_high: float
    inducement: bool
    swept_liquidity: bool
    created_at: datetime

    def width(self) -> float:
        return self.zone_high - self.zone_low


@dataclass
class ProposedOrder:
    poi: POI
    entry: float
    stop: float
    take_profit: float
    direction: str


class SMCStrategy:
    """Simplified SMC detector that respects inducement + swept-liquidity POI rules."""

    def __init__(self):
        self.history: List[Candle] = []
        self._pois: Dict[str, POI] = {}
        self.last_bos_direction: Optional[str] = None

    def _select_zone(self, candle: Candle, direction: str) -> tuple[float, float]:
        wick_is_bigger = candle.wick_top_size > candle.body_size or candle.wick_bottom_size > candle.body_size
        if wick_is_bigger:
            zone_high = candle.high if direction == "short" else candle.body_high
            zone_low = candle.body_low if direction == "long" else candle.low
        else:
            zone_high = candle.body_high
            zone_low = candle.body_low
        if direction == "short" and zone_low > zone_high:
            zone_low, zone_high = zone_high, zone_low
        if direction == "long" and zone_low > zone_high:
            zone_low, zone_high = zone_high, zone_low
        return zone_low, zone_high

    def _inducement_present(self) -> bool:
        if len(self.history) < 2:
            return False
        prev = self.history[-1]
        prev2 = self.history[-2]
        return abs(prev.close - prev2.close) < max(prev.range, prev2.range) * 0.15

    def _sweep_detected(self, candle: Candle) -> Optional[str]:
        if len(self.history) < 2:
            return None
        prev = self.history[-1]
        prev2 = self.history[-2]
        swept_above = candle.high > prev.high >= prev2.high and candle.close < candle.open
        swept_below = candle.low < prev.low <= prev2.low and candle.close > candle.open
        if swept_above:
            return "short"
        if swept_below:
            return "long"
        return None

    def _structure_break_anchor(self, direction: str) -> bool:
        if direction == "short":
            return self.last_bos_direction == "up"
        return self.last_bos_direction == "down"

    def _update_structure_flags(self, candle: Candle) -> None:
        if not self.history:
            return
        prev = self.history[-1]
        if candle.high > prev.high:
            self.last_bos_direction = "up"
        elif candle.low < prev.low:
            self.last_bos_direction = "down"

    def _register_poi(self, candle: Candle, direction: str) -> Optional[POI]:
        zone_low, zone_high = self._select_zone(candle, direction)
        inducement = self._inducement_present()
        swept_liquidity = True  # sweep already detected upstream
        anchored_to_break = self._structure_break_anchor(direction)
        poi_id = f"{candle.timestamp.isoformat()}-{direction}"
        poi = POI(
            id=poi_id,
            direction=direction,
            zone_low=zone_low,
            zone_high=zone_high,
            inducement=inducement,
            swept_liquidity=swept_liquidity and anchored_to_break,
            created_at=candle.timestamp,
        )
        # A POI is tradable only when it pairs swept liquidity with inducement (or at least the sweep).
        if poi.swept_liquidity or inducement:
            self._pois[poi_id] = poi
            return poi
        return None

    def on_candle(self, candle: Candle) -> List[ProposedOrder]:
        orders: List[ProposedOrder] = []
        self._update_structure_flags(candle)
        sweep_direction = self._sweep_detected(candle)
        if sweep_direction:
            poi = self._register_poi(candle, sweep_direction)
            if poi:
                stop_distance = poi.width() or max(0.0005, candle.range * 0.5)
                if sweep_direction == "short":
                    entry = poi.zone_high
                    stop = poi.zone_high + stop_distance
                    take_profit = entry - stop_distance * 5
                else:
                    entry = poi.zone_low
                    stop = poi.zone_low - stop_distance
                    take_profit = entry + stop_distance * 5
                orders.append(
                    ProposedOrder(
                        poi=poi,
                        entry=entry,
                        stop=stop,
                        take_profit=take_profit,
                        direction=sweep_direction,
                    )
                )
        self.history.append(candle)
        return orders

    def open_pois(self) -> List[POI]:
        return list(self._pois.values())
