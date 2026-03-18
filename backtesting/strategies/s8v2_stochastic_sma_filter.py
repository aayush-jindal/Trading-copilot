"""
S8v2: StochasticSmaTrendStrategy

S8 variant — adds an explicit SMA200 uptrend gate as the first required
condition in evaluate(). Hypothesis: stochastic oversold crosses in
uptrends (price > SMA200) are higher quality than counter-trend crosses.

should_enter / get_stops / should_exit are identical to S8.
"""

from backtesting.base import BaseStrategy, Condition, RiskLevels, StrategyResult, StopConfig, Trade
from backtesting.signals import SignalSnapshot


class StochasticSmaTrendStrategy(BaseStrategy):
    name = "S8v2_StochasticSmaTrend"
    type = "reversion"

    def __init__(self):
        self._prev_k: dict[str, float] = {}

    def should_enter(self, snapshot: SignalSnapshot, ticker: str = "") -> bool:
        momentum = snapshot.momentum or {}
        trend = snapshot.trend or {}

        stoch_k = momentum.get("stochastic_k")
        stoch_d = momentum.get("stochastic_d")
        if stoch_k is None or stoch_d is None:
            return False

        prev_k = self._prev_k.get(ticker)
        self._prev_k[ticker] = stoch_k

        if prev_k is None or not (prev_k < 20 and stoch_k >= 20 and stoch_k > stoch_d):
            return False
        if trend.get("price_vs_sma200") != "above":
            return False
        rsi = momentum.get("rsi")
        if rsi is not None and rsi >= 65:
            return False
        return True

    def get_stops(self, snapshot: SignalSnapshot) -> StopConfig:
        price = snapshot.price
        vol = snapshot.volatility or {}
        sr = snapshot.support_resistance or {}
        atr = vol.get("atr") or 0.0

        stop = sr.get("nearest_support") or round(price - atr, 4)
        if atr > 0 and not self._stop_is_valid(price, stop, atr):
            stop = round(price - 1.5 * atr, 4)
        target = round(price + 2.0 * atr, 4)
        raw_risk = price - stop
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0

        return StopConfig(
            entry_price=price,
            stop_loss=round(stop, 4),
            target_1=target,
            risk_reward=round(rr, 3),
        )

    def should_exit(self, snapshot: SignalSnapshot, trade: Trade) -> bool:
        stoch_k = (snapshot.momentum or {}).get("stochastic_k")
        if stoch_k is not None and stoch_k >= 80:
            return True
        return False

    def _check_conditions(self, snapshot) -> list:
        momentum = snapshot.momentum or {}
        trend = snapshot.trend or {}

        stoch_k = momentum.get("stochastic_k") or 0.0
        stoch_d = momentum.get("stochastic_d") or 0.0
        rsi = momentum.get("rsi") or 0.0
        prev_k = self._prev_k.get("", stoch_k)

        return [
            # ONE change vs S8: SMA200 uptrend gate is now the FIRST required condition
            Condition(
                label="Uptrend filter (price above SMA200)",
                passed=trend.get("price_vs_sma200") == "above",
                value="above" if trend.get("price_vs_sma200") == "above" else "below",
                required="above"
            ),
            Condition(
                label="Stochastic K crossed above D from below 20",
                passed=prev_k < 20 and stoch_k >= 20 and stoch_k > stoch_d,
                value=f"K={stoch_k:.1f} D={stoch_d:.1f}",
                required="cross above 20"
            ),
            Condition(
                label="Price above SMA200",
                passed=trend.get("price_vs_sma200") == "above",
                value=trend.get("price_vs_sma200", "N/A"),
                required="above"
            ),
            Condition(
                label="RSI not overbought",
                passed=rsi < 65,
                value=f"RSI {rsi:.1f}",
                required="< 65"
            ),
        ]

    def _compute_risk(self, snapshot) -> object | None:
        vol = snapshot.volatility or {}
        sr = snapshot.support_resistance or {}
        price = snapshot.price
        atr = vol.get("atr")
        if not atr:
            return None
        stop = sr.get("nearest_support") or price - atr
        if not self._stop_is_valid(price, stop, atr):
            return None
        target = price + 2.0 * atr
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
        stoch_k = (snapshot.momentum or {}).get("stochastic_k")
        if stoch_k is not None:
            self._prev_k.setdefault("", stoch_k)

        conditions = self._check_conditions(snapshot)

        if stoch_k is not None:
            self._prev_k[""] = stoch_k

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
