"""
StrategyScanner — runs all registered strategies against live signals.
Returns results ranked by score descending. NO_TRADE results excluded.

Usage:
    from backtesting.scanner import StrategyScanner
    scanner = StrategyScanner()
    results = scanner.scan("AAPL", account_size=50000, risk_pct=0.01)
"""

from datetime import datetime, timedelta

from backtesting.data import YFinanceProvider
from backtesting.signals import SignalEngine
from backtesting.strategies.registry import STRATEGY_REGISTRY


class StrategyScanner:
    def __init__(self):
        self._strategies = STRATEGY_REGISTRY
        self._provider = YFinanceProvider()
        self._engine = SignalEngine()

    def scan(self, ticker: str, account_size: float, risk_pct: float) -> list:
        """Evaluate all registered strategies against the latest signals for ticker.

        Args:
            ticker:       Ticker symbol e.g. "AAPL"
            account_size: Total account value in dollars
            risk_pct:     Fraction of account to risk per trade e.g. 0.01 = 1%

        Returns:
            list[StrategyResult] — WATCH/ENTRY only, sorted by score descending
        """
        print(f"Scanning {ticker}...")
        end = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=500)).strftime("%Y-%m-%d")
        df = self._provider.fetch_daily(ticker, start, end)
        snapshot = self._engine.compute(df)

        results = []
        for strategy in self._strategies:
            result = strategy.evaluate(snapshot)
            if result.verdict == "NO_TRADE":
                continue

            # Compute position size if risk levels are available
            if result.risk is not None:
                entry = result.risk.entry_price
                stop = result.risk.stop_loss
                risk_per_share = entry - stop
                if risk_per_share > 0:
                    dollar_risk = account_size * risk_pct
                    result.risk.position_size = int(dollar_risk / risk_per_share)

            result.strategy_instance = strategy
            results.append(result)

        results.sort(key=lambda r: r.score, reverse=True)
        return results
