"""
S3: BBSqueezeStrategy

Volatility breakout on squeeze resolution. Long only.
Requires the squeeze to have been active on the previous bar so the entry
fires on the actual breakout bar, not mid-squeeze.
"""

from backtesting.base import BaseStrategy, Condition, RiskLevels, StrategyResult, StopConfig, Trade
from backtesting.signals import SignalSnapshot


class BBSqueezeStrategy(BaseStrategy):
    name = "S3_BBSqueeze"
    type = "breakout"

    def __init__(self):
        self._prev_squeeze: dict[str, bool] = {}

    def should_enter(self, snapshot: SignalSnapshot, ticker: str = "") -> bool:
        vol = snapshot.volatility
        bb_squeeze = vol.get("bb_squeeze", False)
        prev_squeeze = self._prev_squeeze.get(ticker, False)

        # Always update state before returning
        self._prev_squeeze[ticker] = bb_squeeze

        # Condition 1: squeeze just resolved this bar
        if not (prev_squeeze is True and bb_squeeze is False):
            return False

        # Condition 2: price broke above upper BB
        bb_upper = vol.get("bb_upper")
        if bb_upper is None or snapshot.price <= bb_upper:
            return False

        # Condition 3: volume confirmation
        volume_ratio = snapshot.volume.get("volume_ratio")
        if volume_ratio is None or volume_ratio < 1.5:
            return False

        # Condition 4: macro trend filter
        if snapshot.trend.get("price_vs_sma200") != "above":
            return False

        return True

    def get_stops(self, snapshot: SignalSnapshot) -> StopConfig:
        price = snapshot.price
        atr = snapshot.volatility.get("atr") or 0.0
        bb_lower = snapshot.volatility.get("bb_lower") or round(price * 0.95, 4)

        target = round(price + 2.0 * atr, 4)
        raw_risk = price - bb_lower
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0

        return StopConfig(
            entry_price=price,
            stop_loss=bb_lower,
            target_1=target,
            risk_reward=round(rr, 3),
        )

    def should_exit(self, snapshot: SignalSnapshot, trade: Trade) -> bool:
        # False breakout: price closed back below upper band
        bb_upper = snapshot.volatility.get("bb_upper")
        if bb_upper is not None and snapshot.price < bb_upper:
            return True

        # OBV turning against us
        if snapshot.volume.get("obv_trend") == "FALLING":
            return True

        return False

    def _check_conditions(self, snapshot) -> list:
        vol = snapshot.volatility or {}
        volume = snapshot.volume or {}
        trend = snapshot.trend or {}

        price = snapshot.price
        bb_squeeze = vol.get("bb_squeeze", False)
        prev_squeeze = self._prev_squeeze.get("", False)
        bb_upper = vol.get("bb_upper") or 0.0
        volume_ratio = volume.get("volume_ratio") or 0.0

        return [
            Condition(
                label="BB squeeze resolved",
                passed=prev_squeeze is True and bb_squeeze is False,
                value="fired" if (prev_squeeze and not bb_squeeze) else "not fired",
                required="squeeze then expand"
            ),
            Condition(
                label="Price above upper band",
                passed=bb_upper > 0 and price > bb_upper,
                value=f"${price:.2f} vs ${bb_upper:.2f}",
                required="above upper band"
            ),
            Condition(
                label="Volume confirmation",
                passed=volume_ratio >= 1.5,
                value=f"{volume_ratio:.2f}x avg",
                required=">= 1.5x avg"
            ),
            Condition(
                label="Price above SMA200",
                passed=trend.get("price_vs_sma200") == "above",
                value=trend.get("price_vs_sma200", "N/A"),
                required="above"
            ),
        ]

    def _compute_risk(self, snapshot) -> object | None:
        vol = snapshot.volatility or {}
        price = snapshot.price
        atr = vol.get("atr")
        if not atr:
            return None
        bb_lower = vol.get("bb_lower") or round(price * 0.95, 4)
        target = price + 2.0 * atr
        raw_risk = price - bb_lower
        rr = (target - price) / raw_risk if raw_risk > 0 else 0.0
        return RiskLevels(
            entry_price=price,
            stop_loss=round(bb_lower, 4),
            target=round(target, 4),
            risk_reward=round(rr, 2),
            atr=atr,
        )

    def evaluate(self, snapshot) -> object:
        # Update squeeze state for scanner context (key "")
        bb_squeeze = (snapshot.volatility or {}).get("bb_squeeze", False)
        prev = self._prev_squeeze.get("", False)
        conditions = self._check_conditions(snapshot)
        # Advance state after reading it
        self._prev_squeeze[""] = bb_squeeze

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
