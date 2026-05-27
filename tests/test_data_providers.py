import pandas as pd

from quant_system.data.providers import normalize_daily_bars


def test_normalize_daily_bars_accepts_akshare_columns():
    raw = pd.DataFrame(
        {
            "日期": ["2024-01-01"],
            "开盘": [10],
            "最高": [11],
            "最低": [9],
            "收盘": [10.5],
            "成交量": [1000],
        }
    )

    frame = normalize_daily_bars(raw, "1")

    assert frame["symbol"].tolist() == ["000001"]
    assert frame["close"].tolist() == [10.5]
