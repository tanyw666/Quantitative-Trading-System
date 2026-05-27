from __future__ import annotations

import pandas as pd


def fetch_daily(symbol: str, start_date: str, end_date: str, adjust: str = "qfq") -> pd.DataFrame:
    """Fetch A-share daily bars from AkShare when the optional dependency is installed."""
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise RuntimeError("AkShare is not installed. Run: python -m pip install -e .[data]") from exc

    raw = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )
    rename_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "振幅": "amplitude",
        "涨跌幅": "pct_change",
        "涨跌额": "change",
        "换手率": "turnover",
    }
    frame = raw.rename(columns=rename_map)
    frame["symbol"] = symbol
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values("date").reset_index(drop=True)
