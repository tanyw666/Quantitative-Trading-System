import pandas as pd

from quant_system.data.cache import save_daily_cache
from quant_system.data.dataset import load_ohlcv_dataset


def test_load_ohlcv_dataset_from_cached_universe(tmp_path):
    universe = tmp_path / "universe.csv"
    universe.write_text("symbol,name\n000001,Demo\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
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
    save_daily_cache(cache_dir, "000001", frame)

    loaded = load_ohlcv_dataset(cache_dir=cache_dir, universe_path=universe)

    assert loaded["symbol"].tolist() == ["000001", "000001"]


def test_load_ohlcv_dataset_adds_universe_metadata_to_cached_frames(tmp_path):
    universe = tmp_path / "universe.csv"
    universe.write_text("symbol,name,industry,board\n000001,Demo,Bank,Main\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
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
    save_daily_cache(cache_dir, "000001", frame)

    loaded = load_ohlcv_dataset(cache_dir=cache_dir, universe_path=universe)

    assert loaded["name"].tolist() == ["Demo", "Demo"]
    assert loaded["industry"].tolist() == ["Bank", "Bank"]
    assert loaded["board"].tolist() == ["Main", "Main"]


def test_load_ohlcv_dataset_strict_fails_missing_cache(tmp_path):
    universe = tmp_path / "universe.csv"
    universe.write_text("symbol,name\n000001,Demo\n", encoding="utf-8")

    try:
        load_ohlcv_dataset(cache_dir=tmp_path / "cache", universe_path=universe, strict=True)
    except FileNotFoundError as exc:
        assert "Missing cached OHLCV data" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError")
