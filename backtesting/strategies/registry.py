"""
Strategy registry — the only place strategies are registered.

To add a strategy:
  1. Create backtesting/strategies/sN_name.py
  2. Import it here and add one line to STRATEGY_REGISTRY.
  Nothing else changes anywhere.
"""
from .s1_trend_pullback import TrendPullbackStrategy
from .s2_rsi_reversion import RSIMeanReversionStrategy
from .s3_bb_squeeze import BBSqueezeStrategy
from .s7_macd_cross import MACDCrossStrategy
from .s8_stochastic_cross import StochasticCrossStrategy
from .s9_ema_cross import EMACrossStrategy
from .s10_golden_cross_pullback import GoldenCrossPullbackStrategy
# future strategies imported here as they are validated

STRATEGY_REGISTRY: list = [
    TrendPullbackStrategy(),
    RSIMeanReversionStrategy(),
    BBSqueezeStrategy(),
    MACDCrossStrategy(),
    StochasticCrossStrategy(),
    EMACrossStrategy(),
    GoldenCrossPullbackStrategy(),
    # new strategies added here after passing backtest gate
]
