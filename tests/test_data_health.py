import pandas as pd

from quant_system.data.health import check_ohlcv_health


def test_check_ohlcv_health_passes_clean_data():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=30),
            "symbol": ["000001"] * 30,
            "open": [10] * 30,
            "high": [11] * 30,
            "low": [9] * 30,
            "close": [10] * 30,
            "volume": [1000] * 30,
        }
    )

    report = check_ohlcv_health(frame, min_rows_per_symbol=30)

    assert report.status == "ok"
    assert report.symbols == 1


def test_check_ohlcv_health_fails_duplicate_dates():
    frame = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01"],
            "symbol": ["000001", "000001"],
            "open": [10, 10],
            "high": [11, 11],
            "low": [9, 9],
            "close": [10, 10],
            "volume": [1000, 1000],
        }
    )

    report = check_ohlcv_health(frame, min_rows_per_symbol=1)

    assert report.status == "fail"
    assert any(issue.name == "duplicates" for issue in report.issues)
