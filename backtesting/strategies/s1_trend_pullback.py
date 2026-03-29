"""
S1: TrendPullbackStrategy

Entry reads swing_setup.verdict directly from ta_engine output.
Zero reimplementation of swing setup logic.
Stop and target are taken unchanged from swing_setup.risk.
"""

from backtesting.base import BaseStrategy, Condition, RiskLevels, StrategyResult, StopConfig, Trade
from backtesting.signals import SignalSnapshot


class TrendPullbackStrategy(BaseStrategy):
    name = "S1_TrendPullback"
    type = "trend"

    def should_enter(self, snapshot: SignalSnapshot) -> bool:
        swing = snapshot.swing_setup
        if swing is None:
            return False
        if swing["verdict"] != "ENTRY":
            return False
        risk = swing.get("risk", {})
        if risk.get("stop_loss") is None:
            return False
        if risk.get("target") is None:
            return False
        return True

    def get_stops(self, snapshot: SignalSnapshot) -> StopConfig:
        swing = snapshot.swing_setup
        risk = swing["risk"]
        stop = risk["stop_loss"]
        target = risk["target"]
        price = snapshot.price
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
        swing = snapshot.swing_setup or {}
        conditions_data = swing.get("conditions", {})
        rr_label = conditions_data.get("rr_label")
        return [
            Condition(
                label="Uptrend (price above SMA50 & 200)",
                passed=conditions_data.get("uptrend_confirmed", False),
                value="confirmed" if conditions_data.get("uptrend_confirmed") else "not confirmed",
                required="confirmed"
            ),
            Condition(
                label="Weekly trend aligned",
                passed=conditions_data.get("weekly_trend_aligned", False),
                value="bullish" if conditions_data.get("weekly_trend_aligned") else "not bullish",
                required="bullish"
            ),
            Condition(
                label=f"ADX {swing.get('adx', 0):.0f}",
                passed=conditions_data.get("adx_strong", False),
                value=f"{swing.get('adx', 0):.1f}",
                required=">= 20 strong"
            ),
            Condition(
                label="RSI cooled from peak",
                passed=conditions_data.get("rsi_pullback", False),
                value=f"RSI {snapshot.momentum.get('rsi', 0):.1f}",
                required="pullback 40-55"
            ),
            Condition(
                label=f"Near support {snapshot.support_resistance.get('nearest_support', '')}",
                passed=conditions_data.get("near_support", False),
                value=snapshot.support_resistance.get("support_strength", ""),
                required="<= 0.75x ATR"
            ),
            Condition(
                label=f"Volume declining ({snapshot.volume.get('volume_ratio', 0):.2f}x avg)",
                passed=conditions_data.get("volume_declining", False),
                value=f"{snapshot.volume.get('volume_ratio', 0):.2f}x · OBV {snapshot.volume.get('obv_trend', '')}",
                required="declining"
            ),
            Condition(
                label="Reversal candle",
                passed=conditions_data.get("reversal_candle", False),
                value="present" if conditions_data.get("reversal_candle") else "none",
                required="bullish pattern"
            ),
            Condition(
                label="Trigger — price breakout",
                passed=conditions_data.get("trigger_fired", False),
                value="fired" if conditions_data.get("trigger_fired") else "waiting",
                required="waiting for breakout"
            ),
            Condition(
                label="R:R quality",
                passed=rr_label not in ("poor", "bad"),
                value=rr_label or "unavailable",
                required="marginal or better",
            ),
        ]

    def _compute_risk(self, snapshot) -> object | None:
        swing = snapshot.swing_setup
        if not swing:
            return None
        rr_label = (swing.get("conditions") or {}).get("rr_label")
        if rr_label == "poor":
            return None
        risk = swing.get("risk", {})
        stop = risk.get("stop_loss")
        target = risk.get("target")
        if stop is None or target is None:
            return None
        entry = snapshot.price
        raw_risk = entry - stop
        rr = (target - entry) / raw_risk if raw_risk > 0 else 0.0
        entry_zone = risk.get("entry_zone", {})
        return RiskLevels(
            entry_price=entry,
            stop_loss=stop,
            target=target,
            risk_reward=round(rr, 2),
            atr=risk.get("atr14"),
            entry_zone_low=entry_zone.get("low") if isinstance(entry_zone, dict) else None,
            entry_zone_high=entry_zone.get("high") if isinstance(entry_zone, dict) else None,
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
