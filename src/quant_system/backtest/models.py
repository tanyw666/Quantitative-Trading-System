from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from quant_system.metrics.performance import calculate_performance


@dataclass(frozen=True)
class Trade:
    date: pd.Timestamp
    symbol: str
    side: str
    price: float
    quantity: int
    fee: float
    reason: str


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: list[Trade] = field(default_factory=list)
    initial_cash: float = 0.0
    final_cash: float = 0.0

    def summary(self) -> dict[str, float | int]:
        return calculate_performance(self.equity_curve, self.trades, self.initial_cash, self.final_cash).to_dict()
