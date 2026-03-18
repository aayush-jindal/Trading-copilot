"""
S7: MACDCrossStrategy

Trend-following entry on MACD bullish crossover, filtered by SMA200,
RSI not extended, and weekly trend bullish.
"""

from backtesting.base import BaseStrategy, Condition, RiskLevels, StrategyResult, StopConfig, Trade
from backtesting.signals import SignalSnapshot


class MACDCrossStrategy(BaseStrategy):
    name = "S7_MACDCross"
    type = "trend"

    def should_enter(self, snapshot: SignalSnapshot) -> bool:
        momentum = snapshot.momentum or {}
        trend = snapshot.trend or {}
        weekly = snapshot.weekly or {}

        if momentum.get("macd_crossover") != "bullish_crossover":
            return False
        if trend.get("price_vs_sma200") != "above":
            return False
        rsi = momentum.get("rsi")
        if rsi is None or not (40 <= rsi <= 60):
            return False
        if weekly.get("weekly_trend") != "BULLISH":
            return False
        return True

    def get_stops(self, snapshot: SignalSnapshot) -> StopConfig:
        price = snapshot.price
        vol = snapshot.volatility or {}
        sr = snapshot.support_resistance or {}
        atr = vol.get("atr") or 0.0

        stop = round(price - atr, 4)
        target = sr.get("nearest_resistance") or round(price + 2.0 * atr, 4)
        raw_risk = price - stop
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0

        return StopConfig(
            entry_price=price,
            stop_loss=stop,
            target_1=round(target, 4),
            risk_reward=round(rr, 3),
        )

    def should_exit(self, snapshot: SignalSnapshot, trade: Trade) -> bool:
        if snapshot.momentum.get("macd_crossover") == "bearish_crossover":
            return True
        rsi = snapshot.momentum.get("rsi")
        if rsi is not None and rsi >= 70:
            return True
        return False

    def _check_conditions(self, snapshot) -> list:
        momentum = snapshot.momentum or {}
        trend = snapshot.trend or {}
        weekly = snapshot.weekly or {}

        rsi = momentum.get("rsi") or 0.0
        dist = trend.get("distance_from_sma200_pct") or 0.0

        return [
            Condition(
                label="MACD bullish crossover",
                passed=momentum.get("macd_crossover") == "bullish_crossover",
                value=momentum.get("macd_crossover", "none"),
                required="bullish_crossover"
            ),
            Condition(
                label="Price above SMA200",
                passed=trend.get("price_vs_sma200") == "above",
                value=f"{dist:.1f}% above",
                required="above"
            ),
            Condition(
                label="RSI not extended (40-60)",
                passed=40 <= rsi <= 60,
                value=f"RSI {rsi:.1f}",
                required="40-60 zone"
            ),
            Condition(
                label="Weekly trend bullish",
                passed=weekly.get("weekly_trend") == "BULLISH",
                value=weekly.get("weekly_trend", "N/A"),
                required="BULLISH"
            ),
        ]

    def _compute_risk(self, snapshot) -> object | None:
        vol = snapshot.volatility or {}
        sr = snapshot.support_resistance or {}
        price = snapshot.price
        atr = vol.get("atr")
        if not atr:
            return None
        stop = price - atr
        target = sr.get("nearest_resistance") or price + 2.0 * atr
        raw_risk = price - stop
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0
        return RiskLevels(
            entry_price=price,
            stop_loss=round(stop, 4),
            target=round(target, 4),
            risk_reward=round(rr, 2),
            atr=atr,
        )

    def evaluate(self, snapshot) -> object:
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
