import pandas as pd

from quant_system.data.cache import load_daily_cache, save_daily_cache, symbol_cache_path


def test_save_and_load_daily_cache(tmp_path):
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=2),
            "symbol": ["000001", "000001"],
            "open": [10, 11],
            "high": [11, 12],
            "low": [9, 10],
            "close": [10.5, 11.5],
            "volume": [1000, 1200],
        }
    )

    path = save_daily_cache(tmp_path, "000001", frame)
    loaded = load_daily_cache(tmp_path, "000001")

    assert path.with_suffix("") == symbol_cache_path(tmp_path, "000001")
    assert loaded["symbol"].tolist() == ["000001", "000001"]
    assert loaded["close"].tolist() == [10.5, 11.5]
