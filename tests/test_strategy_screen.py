import pandas as pd

from quant_system.strategies.strong_stock_screen import StrongStockScreen


def test_strong_stock_screen_selects_latest_qualified_symbol():
    dates = pd.date_range("2024-01-01", periods=25)
    frame = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "symbol": ["AAA"] * 25 + ["BBB"] * 25,
            "open": list(range(10, 35)) + [10] * 25,
            "high": list(range(11, 36)) + [11] * 25,
            "low": list(range(9, 34)) + [9] * 25,
            "close": list(range(10, 35)) + [10] * 25,
            "volume": ([1000] * 24 + [3000]) + [1000] * 25,
        }
    )
    strategy = StrongStockScreen(min_20d_return=0.1, min_volume_ratio=1.2, max_atr_pct=0.2)

    selected = strategy.screen(frame)

    assert selected["symbol"].tolist() == ["AAA"]
