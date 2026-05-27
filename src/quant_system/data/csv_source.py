from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant_system.data.schema import REQUIRED_OHLCV_COLUMNS, validate_ohlcv


def read_ohlcv_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"symbol": str})
    frame.columns = [str(col).strip().lower() for col in frame.columns]
    report = validate_ohlcv(frame)
    if not report.ok:
        raise ValueError(f"Invalid OHLCV data: {report}")

    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    if "symbol" in frame.columns:
        frame["symbol"] = frame["symbol"].str.strip().str.zfill(6)
    numeric_columns = [col for col in REQUIRED_OHLCV_COLUMNS if col != "date"]
    for col in numeric_columns:
        frame[col] = pd.to_numeric(frame[col], errors="raise")

    sort_columns = ["date"]
    if "symbol" in frame.columns:
        sort_columns = ["symbol", "date"]
    return frame.sort_values(sort_columns).reset_index(drop=True)
