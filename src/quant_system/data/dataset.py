from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant_system.data.cache import load_daily_cache
from quant_system.data.csv_source import read_ohlcv_csv
from quant_system.data.schema import REQUIRED_OHLCV_COLUMNS
from quant_system.data.universe import StockInfo, read_universe


def load_ohlcv_dataset(
    csv_path: Path | None = None,
    cache_dir: Path | None = None,
    universe_path: Path | None = None,
    strict: bool = False,
) -> pd.DataFrame:
    if csv_path:
        return read_ohlcv_csv(csv_path)

    if not cache_dir or not universe_path:
        raise ValueError("Provide either --csv or both --cache-dir and --universe")

    frames = []
    missing = []
    for stock in read_universe(universe_path):
        try:
            frame = _prepare_cached_universe_frame(load_daily_cache(cache_dir, stock.symbol), stock)
            frames.append(frame)
        except FileNotFoundError:
            missing.append(stock.symbol)

    if strict and missing:
        raise FileNotFoundError(f"Missing cached OHLCV data for symbols: {', '.join(missing[:20])}")

    if not frames:
        raise FileNotFoundError(f"No cached OHLCV data found. Missing symbols: {missing}")

    data = pd.concat(frames, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
    return data


def _prepare_cached_universe_frame(frame: pd.DataFrame, stock: StockInfo) -> pd.DataFrame:
    data = frame.copy()
    missing = [column for column in REQUIRED_OHLCV_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError(f"Cached OHLCV for {stock.symbol} is missing columns: {', '.join(missing)}")
    if "symbol" not in data.columns:
        data["symbol"] = stock.symbol
    data["symbol"] = data["symbol"].astype(str).str.strip().str.zfill(6)
    expected = str(stock.symbol).zfill(6)
    mismatched = sorted(symbol for symbol in data["symbol"].dropna().unique() if symbol != expected)
    if mismatched:
        raise ValueError(f"Cached OHLCV for {expected} contains mismatched symbols: {', '.join(mismatched[:5])}")
    data["symbol"] = expected
    data["date"] = pd.to_datetime(data["date"], errors="raise")
    if data[["symbol", "date"]].duplicated().any():
        raise ValueError(f"Cached OHLCV for {expected} contains duplicate symbol+date rows")
    for column in ("name", "market", "board", "industry", "sector"):
        value = getattr(stock, column)
        if not value:
            continue
        if column not in data.columns:
            data[column] = value
        else:
            data[column] = data[column].where(data[column].notna() & (data[column].astype(str).str.strip() != ""), value)
    return data
