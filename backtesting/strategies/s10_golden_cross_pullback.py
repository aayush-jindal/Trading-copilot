"""
S10: GoldenCrossPullbackStrategy

Entry on pullback to SMA50 following a recent golden cross (SMA50 > SMA200),
confirmed by moderate RSI and rising OBV.
"""

from backtesting.base import BaseStrategy, Condition, RiskLevels, StrategyResult, StopConfig, Trade
from backtesting.signals import SignalSnapshot


class GoldenCrossPullbackStrategy(BaseStrategy):
    name = "S10_GoldenCrossPullback"
    type = "trend"

    def __init__(self):
        self._bars_since_cross: dict[str, int] = {}

    def should_enter(self, snapshot: SignalSnapshot, ticker: str = "") -> bool:
        trend = snapshot.trend or {}
        momentum = snapshot.momentum or {}
        volume = snapshot.volume or {}

        golden_cross = trend.get("golden_cross", False)
        bars = self._bars_since_cross.get(ticker, 999)

        if golden_cross:
            bars = 0
        else:
            bars += 1
        self._bars_since_cross[ticker] = bars

        if bars > 10:
            return False

        price = snapshot.price
        sma50 = trend.get("sma_50")
        if sma50 is None or abs(price - sma50) / price >= 0.02:
            return False

        rsi = momentum.get("rsi")
        if rsi is None or not (45 <= rsi <= 65):
            return False

        if volume.get("obv_trend") != "RISING":
            return False

        return True

    def get_stops(self, snapshot: SignalSnapshot) -> StopConfig:
        price = snapshot.price
        trend = snapshot.trend or {}
        vol = snapshot.volatility or {}
        sr = snapshot.support_resistance or {}
        atr = vol.get("atr") or 0.0

        sma50 = trend.get("sma_50") or round(price - atr, 4)
        if atr > 0 and not self._stop_is_valid(price, sma50, atr):
            sma50 = round(price - 1.5 * atr, 4)
        target = sr.get("52w_high") or round(price + 3.0 * atr, 4)
        raw_risk = price - sma50
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0

        return StopConfig(
            entry_price=price,
            stop_loss=round(sma50, 4),
            target_1=round(target, 4),
            risk_reward=round(rr, 3),
        )

    def should_exit(self, snapshot: SignalSnapshot, trade: Trade) -> bool:
        trend = snapshot.trend or {}
        price = snapshot.price
        sma50 = trend.get("sma_50")
        if sma50 is not None and price < sma50:
            return True
        rsi = snapshot.momentum.get("rsi")
        if rsi is not None and rsi >= 70:
            return True
        nearest_resistance = snapshot.support_resistance.get("nearest_resistance")
        if nearest_resistance and price >= nearest_resistance:
            return True
        return False

    def _check_conditions(self, snapshot) -> list:
        trend = snapshot.trend or {}
        momentum = snapshot.momentum or {}
        volume = snapshot.volume or {}
        price = snapshot.price

        golden_cross = trend.get("golden_cross", False)
        bars = self._bars_since_cross.get("", 999)
        sma50 = trend.get("sma_50") or 0.0
        rsi = momentum.get("rsi") or 0.0

        near_sma50 = sma50 > 0 and abs(price - sma50) / price < 0.02

        return [
            Condition(
                label="Golden cross recent (within 10 bars)",
                passed=bars <= 10,
                value=f"{bars} bars ago" if bars <= 10 else "not recent",
                required="within 10 bars"
            ),
            Condition(
                label="Price pulled back to SMA50",
                passed=near_sma50,
                value=f"${price:.2f} vs SMA50 ${sma50:.2f}",
                required="within 2% of SMA50"
            ),
            Condition(
                label="RSI moderate (45-65)",
                passed=45 <= rsi <= 65,
                value=f"RSI {rsi:.1f}",
                required="45-65"
            ),
            Condition(
                label="OBV rising",
                passed=volume.get("obv_trend") == "RISING",
                value=volume.get("obv_trend", "N/A"),
                required="RISING"
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
        sma50 = trend.get("sma_50") or price - atr
        if not self._stop_is_valid(price, sma50, atr):
            return None
        target = sr.get("52w_high") or price + 3.0 * atr
        raw_risk = price - sma50
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0
        return RiskLevels(
            entry_price=price,
            stop_loss=round(sma50, 4),
            target=round(target, 4),
            risk_reward=round(rr, 2),
            atr=atr,
        )

    def evaluate(self, snapshot) -> object:
        trend = snapshot.trend or {}
        golden_cross = trend.get("golden_cross", False)
        bars = self._bars_since_cross.get("", 999)

        # Advance state before check so _check_conditions sees updated count
        if golden_cross:
            bars = 0
        else:
            bars = bars + 1 if bars < 999 else 999
        self._bars_since_cross[""] = bars

        conditions = self._check_conditions(snapshot)
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
