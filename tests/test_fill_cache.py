from pathlib import Path

import pandas as pd

from quant_system.data.cache import save_daily_cache
from quant_system.data.universe import StockInfo
from tools.fill_cache import target_symbols


def _frame(date_text: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [date_text],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "volume": [1000.0],
            "symbol": ["000001"],
        }
    )


def test_target_symbols_returns_missing_and_stale_entries(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    universe = [
        StockInfo(symbol="000001", name="A"),
        StockInfo(symbol="000002", name="B"),
        StockInfo(symbol="000003", name="C"),
    ]

    fresh = _frame("2026-05-28")
    fresh["symbol"] = ["000001"]
    save_daily_cache(cache_dir, "000001", fresh)

    stale = _frame("2026-05-20")
    stale["symbol"] = ["000002"]
    save_daily_cache(cache_dir, "000002", stale)

    targets = target_symbols(universe, cache_dir, "20260529", refresh_stale_days=3)

    assert targets == ["000002", "000003"]


def test_target_symbols_refresh_all_includes_everything(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    universe = [StockInfo(symbol="000001", name="A"), StockInfo(symbol="000002", name="B")]
    save_daily_cache(cache_dir, "000001", _frame("2026-05-28"))

    targets = target_symbols(universe, cache_dir, "20260529", refresh_all=True)

    assert targets == ["000001", "000002"]
