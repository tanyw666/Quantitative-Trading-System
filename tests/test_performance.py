import pandas as pd

from quant_system.backtest.models import Trade
from quant_system.metrics.performance import calculate_performance, realized_trade_pnls


def test_realized_trade_pnls_matches_buy_sell_pairs():
    trades = [
        Trade(pd.Timestamp("2024-01-01"), "000001", "BUY", 10, 100, 1, "buy"),
        Trade(pd.Timestamp("2024-01-02"), "000001", "SELL", 12, 100, 1, "sell"),
    ]

    assert realized_trade_pnls(trades) == [198.0]


def test_calculate_performance_includes_win_rate():
    equity = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=2),
            "equity": [10000, 10200],
        }
    )
    trades = [
        Trade(pd.Timestamp("2024-01-01"), "000001", "BUY", 10, 100, 1, "buy"),
        Trade(pd.Timestamp("2024-01-02"), "000001", "SELL", 12, 100, 1, "sell"),
    ]

    summary = calculate_performance(equity, trades, initial_cash=10000, final_cash=10200)

    assert abs(summary.total_return - 0.02) < 1e-12
    assert summary.win_rate == 1.0
