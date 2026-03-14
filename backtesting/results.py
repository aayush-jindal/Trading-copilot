"""
ResultsAnalyzer — statistics, summary table, CSV export, and Phase 1 gate check.
"""

import csv
from dataclasses import dataclass

from backtesting.engine import TradeLog
from backtesting.base import Trade


@dataclass
class StrategyStats:
    strategy_name: str
    ticker: str
    total_trades: int
    win_rate: float        # 0.0–1.0
    avg_rr: float          # average R-multiple across all closed trades
    expectancy: float      # win_rate * avg_win_r + (1 - win_rate) * avg_loss_r
    max_drawdown_r: float  # largest peak-to-trough in cumulative R
    profit_factor: float   # gross profit / gross loss (0 if no losses)


class ResultsAnalyzer:
    def __init__(self, trade_logs: list[TradeLog]):
        self._logs = trade_logs

    def compute(self) -> list[StrategyStats]:
        stats = []
        for log in self._logs:
            trades = [t for t in log.trades if t.pnl_r is not None]
            n = len(trades)
            if n == 0:
                stats.append(StrategyStats(
                    strategy_name=log.strategy_name,
                    ticker=log.ticker,
                    total_trades=0,
                    win_rate=0.0,
                    avg_rr=0.0,
                    expectancy=0.0,
                    max_drawdown_r=0.0,
                    profit_factor=0.0,
                ))
                continue

            pnls = [t.pnl_r for t in trades]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]

            win_rate = len(wins) / n
            avg_rr = sum(pnls) / n
            avg_win_r = sum(wins) / len(wins) if wins else 0.0
            avg_loss_r = sum(losses) / len(losses) if losses else 0.0
            expectancy = win_rate * avg_win_r + (1 - win_rate) * avg_loss_r

            gross_profit = sum(wins)
            gross_loss = abs(sum(losses))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

            # Max drawdown in R (peak-to-trough of cumulative R curve)
            cum_r = 0.0
            peak = 0.0
            max_dd = 0.0
            for p in pnls:
                cum_r += p
                if cum_r > peak:
                    peak = cum_r
                dd = peak - cum_r
                if dd > max_dd:
                    max_dd = dd

            stats.append(StrategyStats(
                strategy_name=log.strategy_name,
                ticker=log.ticker,
                total_trades=n,
                win_rate=round(win_rate, 4),
                avg_rr=round(avg_rr, 4),
                expectancy=round(expectancy, 4),
                max_drawdown_r=round(max_dd, 4),
                profit_factor=round(profit_factor, 4),
            ))
        return stats

    def summary(self) -> None:
        stats = self.compute()
        header = f"{'Strategy':<20} {'Ticker':<8} {'Trades':>7} {'Win%':>6} {'AvgR':>7} {'Expect':>8} {'MaxDD_R':>9} {'PF':>7}"
        print(header)
        print("-" * len(header))
        for s in stats:
            gate = " ✓" if self.passes_gate(s) else "  "
            print(
                f"{s.strategy_name:<20} {s.ticker:<8} {s.total_trades:>7} "
                f"{s.win_rate*100:>5.1f}% {s.avg_rr:>7.3f} {s.expectancy:>8.3f} "
                f"{s.max_drawdown_r:>9.3f} {s.profit_factor:>7.3f}{gate}"
            )

    def to_csv(self, path: str) -> None:
        all_trades: list[Trade] = []
        for log in self._logs:
            all_trades.extend(log.trades)

        fieldnames = [
            "strategy", "ticker", "entry_date", "entry_price",
            "exit_date", "exit_price", "exit_reason",
            "stop_loss", "target_1", "pnl_r",
        ]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in all_trades:
                writer.writerow({
                    "strategy": next(
                        (l.strategy_name for l in self._logs if t in l.trades), ""
                    ),
                    "ticker": t.ticker,
                    "entry_date": t.entry_date,
                    "entry_price": t.entry_price,
                    "exit_date": t.exit_date,
                    "exit_price": t.exit_price,
                    "exit_reason": t.exit_reason,
                    "stop_loss": t.stop_loss,
                    "target_1": t.target_1,
                    "pnl_r": t.pnl_r,
                })

    @staticmethod
    def passes_gate(stats: StrategyStats) -> bool:
        """Phase 1 gate: 30+ trades AND positive expectancy."""
        return stats.total_trades >= 30 and stats.expectancy > 0
