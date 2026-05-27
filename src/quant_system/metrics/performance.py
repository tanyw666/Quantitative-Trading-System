from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class PerformanceSummary:
    initial_cash: float
    final_equity: float
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe: float
    max_drawdown: float
    trades: int
    win_rate: float
    profit_factor: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "initial_cash": self.initial_cash,
            "final_equity": self.final_equity,
            "total_return": self.total_return,
            "annualized_return": self.annualized_return,
            "annualized_volatility": self.annualized_volatility,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "trades": self.trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
        }


def calculate_performance(equity_curve: pd.DataFrame, trades: list, initial_cash: float, final_cash: float) -> PerformanceSummary:
    if equity_curve.empty:
        return PerformanceSummary(initial_cash, final_cash, 0.0, 0.0, 0.0, 0.0, 0.0, len(trades), 0.0, 0.0)

    equity = equity_curve["equity"].astype(float)
    final_equity = float(equity.iloc[-1])
    total_return = final_equity / initial_cash - 1.0 if initial_cash else 0.0
    daily_returns = equity.pct_change().dropna()

    if daily_returns.empty:
        annualized_volatility = 0.0
        sharpe = 0.0
    else:
        annualized_volatility = float(daily_returns.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR))
        sharpe = float(daily_returns.mean() / daily_returns.std(ddof=0) * math.sqrt(TRADING_DAYS_PER_YEAR)) if daily_returns.std(ddof=0) else 0.0

    years = max(len(equity) / TRADING_DAYS_PER_YEAR, 1 / TRADING_DAYS_PER_YEAR)
    annualized_return = float((1 + total_return) ** (1 / years) - 1) if total_return > -1 else -1.0

    peak = equity.cummax()
    drawdown = equity / peak - 1.0
    max_drawdown = float(drawdown.min())

    realized_pnls = realized_trade_pnls(trades)
    wins = [pnl for pnl in realized_pnls if pnl > 0]
    losses = [pnl for pnl in realized_pnls if pnl < 0]
    win_rate = len(wins) / len(realized_pnls) if realized_pnls else 0.0
    profit_factor = sum(wins) / abs(sum(losses)) if losses else (float("inf") if wins else 0.0)

    return PerformanceSummary(
        initial_cash=initial_cash,
        final_equity=final_equity,
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        max_drawdown=max_drawdown,
        trades=len(trades),
        win_rate=win_rate,
        profit_factor=profit_factor,
    )


def realized_trade_pnls(trades: list) -> list[float]:
    open_lots: dict[str, list[Trade]] = {}
    pnls: list[float] = []

    for trade in trades:
        if trade.side == "BUY":
            open_lots.setdefault(trade.symbol, []).append(trade)
            continue

        remaining = trade.quantity
        lots = open_lots.get(trade.symbol, [])
        while remaining > 0 and lots:
            buy = lots[0]
            matched = min(remaining, buy.quantity)
            pnl = (trade.price - buy.price) * matched
            pnl -= buy.fee * (matched / buy.quantity)
            pnl -= trade.fee * (matched / trade.quantity)
            pnls.append(float(pnl))
            remaining -= matched
            if matched == buy.quantity:
                lots.pop(0)
            else:
                remaining_ratio = (buy.quantity - matched) / buy.quantity
                lots[0] = type(buy)(
                    buy.date,
                    buy.symbol,
                    buy.side,
                    buy.price,
                    buy.quantity - matched,
                    buy.fee * remaining_ratio,
                    buy.reason,
                )

    return pnls
