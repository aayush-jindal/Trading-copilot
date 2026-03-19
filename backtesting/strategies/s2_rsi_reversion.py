"""
S2: RSIMeanReversionStrategy

Mean reversion in uptrend. Enters on RSI crossover above 30 from oversold,
filtered by SMA200 and BB position. Exit on RSI >= 55.
"""

from backtesting.base import BaseStrategy, Condition, RiskLevels, StrategyResult, StopConfig, Trade
from backtesting.signals import SignalSnapshot


class RSIMeanReversionStrategy(BaseStrategy):
    name = "S2_RSIMeanReversion"
    type = "reversion"

    def __init__(self):
        self._prev_rsi: dict[str, float] = {}

    def should_enter(self, snapshot: SignalSnapshot, ticker: str = "") -> bool:
        rsi = snapshot.momentum.get("rsi")
        if rsi is None:
            self._prev_rsi[ticker] = rsi
            return False

        prev_rsi = self._prev_rsi.get(ticker)

        # Always update state before returning
        self._prev_rsi[ticker] = rsi

        # Condition 1: RSI crossed up through 30 this bar
        if prev_rsi is None or not (prev_rsi < 30 and rsi >= 30):
            return False

        # Condition 2: price above SMA200 (no mean reversion in downtrends)
        if snapshot.trend.get("price_vs_sma200") != "above":
            return False

        # Condition 3: BB position below 20 (price still near lower band)
        bb_pos = snapshot.volatility.get("bb_position")
        if bb_pos is None or bb_pos >= 20:
            return False

        return True

    def get_stops(self, snapshot: SignalSnapshot) -> StopConfig:
        price = snapshot.price
        atr = snapshot.volatility.get("atr") or 0.0
        bb_middle = snapshot.volatility.get("bb_middle")

        stop = round(price - 1.5 * atr, 4)
        target = round(bb_middle, 4) if bb_middle else round(price + 2.0 * atr, 4)

        raw_risk = price - stop
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0

        return StopConfig(
            entry_price=price,
            stop_loss=stop,
            target_1=target,
            risk_reward=round(rr, 3),
        )

    def should_exit(self, snapshot: SignalSnapshot, trade: Trade) -> bool:
        rsi = snapshot.momentum.get("rsi")
        if rsi is not None and rsi >= 65:
            return True
        nearest_resistance = snapshot.support_resistance.get("nearest_resistance")
        if nearest_resistance and snapshot.price >= nearest_resistance:
            return True
        return False

    def _check_conditions(self, snapshot) -> list:
        trend = snapshot.trend or {}
        momentum = snapshot.momentum or {}
        volatility = snapshot.volatility or {}

        rsi = momentum.get("rsi", 0.0) or 0.0
        prev_rsi = self._prev_rsi.get("", rsi)
        bb_pos = volatility.get("bb_position", 100.0) or 100.0

        return [
            Condition(
                label="Price above SMA200",
                passed=trend.get("price_vs_sma200") == "above",
                value=f"{trend.get('distance_from_sma200_pct') or 0:.1f}%",
                required="above"
            ),
            Condition(
                label="RSI crossed above 30",
                passed=prev_rsi < 30 and rsi >= 30,
                value=f"RSI {rsi:.1f} (was {prev_rsi:.1f})",
                required="cross above 30"
            ),
            Condition(
                label="BB position below 20",
                passed=bb_pos < 20,
                value=f"pos {bb_pos:.0f}%",
                required="< 20%"
            ),
        ]

    def _compute_risk(self, snapshot) -> object | None:
        price = snapshot.price
        volatility = snapshot.volatility or {}
        atr = volatility.get("atr")
        if not atr:
            return None
        stop = price - 1.5 * atr
        if not self._stop_is_valid(price, stop, atr):
            return None
        bb_middle = volatility.get("bb_middle")
        target = bb_middle if bb_middle else price + 2.0 * atr
        raw_risk = price - stop
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0
        # Entry zone from swing_setup support — same logic as S1 (price at support on oversold)
        swing = snapshot.swing_setup or {}
        entry_zone = swing.get("risk", {}).get("entry_zone", {})
        return RiskLevels(
            entry_price=price,
            stop_loss=round(stop, 4),
            target=round(target, 4),
            risk_reward=round(rr, 2),
            atr=atr,
            entry_zone_low=entry_zone.get("low") if isinstance(entry_zone, dict) else None,
            entry_zone_high=entry_zone.get("high") if isinstance(entry_zone, dict) else None,
        )

    def evaluate(self, snapshot) -> object:
        # Update prev_rsi state for scanner context (key "")
        rsi = snapshot.momentum.get("rsi")
        if rsi is not None:
            self._prev_rsi[""] = self._prev_rsi.get("", rsi)

        conditions = self._check_conditions(snapshot)
        verdict, score = self._verdict(conditions)

        # Update state after evaluation
        if rsi is not None:
            self._prev_rsi[""] = rsi

        risk = self._compute_risk(snapshot) if verdict != "NO_TRADE" else None
        return StrategyResult(
            name=self.name,
            type=self.type,
            verdict=verdict,
            score=score,
            conditions=conditions,
            risk=risk,
        )
