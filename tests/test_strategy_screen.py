import pandas as pd

from quant_system.strategies.strong_stock_screen import StrongStockScreen
from quant_system.strategies.trend_breakout import TrendBreakoutStrategy


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


def test_strong_stock_screen_blocks_overextended_candidate():
    dates = pd.date_range("2024-01-01", periods=30)
    frame = pd.DataFrame(
        {
            "date": dates,
            "symbol": ["AAA"] * 30,
            "open": [10] * 25 + [20, 21, 22, 23, 24],
            "high": [11] * 25 + [21, 22, 23, 24, 25],
            "low": [9] * 25 + [19, 20, 21, 22, 23],
            "close": [10] * 25 + [20, 21, 22, 23, 24],
            "volume": [1000] * 29 + [3000],
        }
    )
    strategy = StrongStockScreen(
        min_20d_return=0.1,
        min_volume_ratio=1.2,
        max_atr_pct=0.8,
        max_close_ma20_gap=0.2,
    )

    selected = strategy.screen(frame)

    assert selected.empty


def test_strong_stock_screen_blocks_false_breakout_distribution():
    dates = pd.date_range("2024-01-01", periods=25)
    frame = pd.DataFrame(
        {
            "date": dates,
            "symbol": ["AAA"] * 25,
            "open": list(range(10, 34)) + [33],
            "high": list(range(11, 35)) + [36],
            "low": list(range(9, 33)) + [32],
            "close": list(range(10, 34)) + [33.5],
            "volume": [1000] * 24 + [3000],
        }
    )
    strategy = StrongStockScreen(
        min_20d_return=0.1,
        min_volume_ratio=1.2,
        max_atr_pct=0.3,
        max_candle_warning_count=0,
    )

    selected = strategy.screen(frame)

    assert selected.empty



def test_trend_breakout_selects_clean_confirmed_breakout():
    dates = pd.date_range("2024-01-01", periods=25)
    closes = list(range(10, 34)) + [35]
    frame = pd.DataFrame(
        {
            "date": dates,
            "symbol": ["AAA"] * 25,
            "open": [value - 0.2 for value in closes],
            "high": [value + 0.5 for value in closes],
            "low": [value - 0.5 for value in closes],
            "close": closes,
            "volume": [1000] * 24 + [2200],
        }
    )
    strategy = TrendBreakoutStrategy(
        min_momentum=0.1,
        max_atr_pct=0.2,
        max_close_ma20_gap=0.5,
        min_entry_structure_score=50,
    )

    selected = strategy.screen(frame)

    assert selected["symbol"].tolist() == ["AAA"]
    assert selected["entry_structure_score"].iloc[0] >= 50


def test_trend_breakout_blocks_exhaustion_breakout():
    dates = pd.date_range("2024-01-01", periods=25)
    closes = list(range(10, 34)) + [35]
    frame = pd.DataFrame(
        {
            "date": dates,
            "symbol": ["AAA"] * 25,
            "open": list(range(10, 34)) + [34],
            "high": [value + 0.5 for value in range(10, 34)] + [45],
            "low": [value - 0.5 for value in range(10, 34)] + [33],
            "close": closes,
            "volume": [1000] * 24 + [3000],
        }
    )
    strategy = TrendBreakoutStrategy(
        min_momentum=0.1,
        max_atr_pct=0.5,
        max_close_ma20_gap=0.5,
        max_candle_warning_count=0,
    )

    selected = strategy.screen(frame)

    assert selected.empty
