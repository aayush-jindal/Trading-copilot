"""
S9: EMACrossStrategy

Trend entry on EMA9 crossing above EMA21, confirmed by price above both
EMAs, SMA200, and volume not weak.
"""

from backtesting.base import BaseStrategy, Condition, RiskLevels, StrategyResult, StopConfig, Trade
from backtesting.signals import SignalSnapshot


class EMACrossStrategy(BaseStrategy):
    name = "S9_EMACross"
    type = "trend"

    def __init__(self):
        self._prev_ema9: dict[str, float] = {}
        self._prev_ema21: dict[str, float] = {}

    def should_enter(self, snapshot: SignalSnapshot, ticker: str = "") -> bool:
        trend = snapshot.trend or {}
        volume = snapshot.volume or {}

        ema9 = trend.get("ema_9")
        ema21 = trend.get("ema_21")
        if ema9 is None or ema21 is None:
            return False

        prev9 = self._prev_ema9.get(ticker)
        prev21 = self._prev_ema21.get(ticker)
        self._prev_ema9[ticker] = ema9
        self._prev_ema21[ticker] = ema21

        if prev9 is None or prev21 is None:
            return False
        if not (prev9 <= prev21 and ema9 > ema21):
            return False

        price = snapshot.price
        if price <= ema9 or price <= ema21:
            return False
        if trend.get("price_vs_sma200") != "above":
            return False
        vol_ratio = volume.get("volume_ratio") or 0.0
        if vol_ratio < 1.0:
            return False
        return True

    def get_stops(self, snapshot: SignalSnapshot) -> StopConfig:
        price = snapshot.price
        trend = snapshot.trend or {}
        vol = snapshot.volatility or {}
        sr = snapshot.support_resistance or {}
        atr = vol.get("atr") or 0.0

        ema21 = trend.get("ema_21") or round(price - atr, 4)
        if atr > 0 and not self._stop_is_valid(price, ema21, atr):
            ema21 = round(price - 1.5 * atr, 4)
        target = sr.get("nearest_resistance") or round(price + 2.0 * atr, 4)
        raw_risk = price - ema21
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0

        return StopConfig(
            entry_price=price,
            stop_loss=round(ema21, 4),
            target_1=round(target, 4),
            risk_reward=round(rr, 3),
        )

    def should_exit(self, snapshot: SignalSnapshot, trade: Trade) -> bool:
        trend = snapshot.trend or {}
        ema9 = trend.get("ema_9")
        ema21 = trend.get("ema_21")
        if ema9 is not None and ema21 is not None and ema9 < ema21:
            return True
        return False

    def _check_conditions(self, snapshot) -> list:
        trend = snapshot.trend or {}
        volume = snapshot.volume or {}
        price = snapshot.price

        ema9 = trend.get("ema_9") or 0.0
        ema21 = trend.get("ema_21") or 0.0
        vol_ratio = volume.get("volume_ratio") or 0.0
        prev9 = self._prev_ema9.get("", ema9)
        prev21 = self._prev_ema21.get("", ema21)

        return [
            Condition(
                label="EMA9 crossed above EMA21",
                passed=prev9 <= prev21 and ema9 > ema21,
                value=f"EMA9={ema9:.2f} EMA21={ema21:.2f}",
                required="EMA9 > EMA21 crossover"
            ),
            Condition(
                label="Price above both EMAs",
                passed=ema9 > 0 and ema21 > 0 and price > ema9 and price > ema21,
                value=f"${price:.2f}",
                required="above EMA9 and EMA21"
            ),
            Condition(
                label="Price above SMA200",
                passed=trend.get("price_vs_sma200") == "above",
                value=trend.get("price_vs_sma200", "N/A"),
                required="above"
            ),
            Condition(
                label="Volume not weak",
                passed=vol_ratio >= 1.0,
                value=f"{vol_ratio:.2f}x",
                required=">= 1.0x avg"
            ),
        ]

    def _compute_risk(self, snapshot) -> object | None:
        trend = snapshot.trend or {}
        vol = snapshot.volatility or {}
        sr = snapshot.support_resistance or {}
        price = snapshot.price
        atr = vol.get("atr")
        if not atr:
            return None
        ema21 = trend.get("ema_21") or price - atr
        if not self._stop_is_valid(price, ema21, atr):
            return None
        target = sr.get("nearest_resistance") or price + 2.0 * atr
        raw_risk = price - ema21
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0
        return RiskLevels(
            entry_price=price,
            stop_loss=round(ema21, 4),
            target=round(target, 4),
            risk_reward=round(rr, 2),
            atr=atr,
        )

    def evaluate(self, snapshot) -> object:
        trend = snapshot.trend or {}
        ema9 = trend.get("ema_9")
        ema21 = trend.get("ema_21")
        if ema9 is not None:
            self._prev_ema9.setdefault("", ema9)
        if ema21 is not None:
            self._prev_ema21.setdefault("", ema21)

        conditions = self._check_conditions(snapshot)

        if ema9 is not None:
            self._prev_ema9[""] = ema9
        if ema21 is not None:
            self._prev_ema21[""] = ema21

        verdict, score = self._verdict(conditions)
        risk = self._compute_risk(snapshot) if verdict != "NO_TRADE" else None
        return StrategyResult(
            name=self.name,
            type=self.type,
            verdict=verdict,
            score=score,
            conditions=conditions,
            risk=risk,
        )
