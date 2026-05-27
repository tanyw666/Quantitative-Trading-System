from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant_system.data.cache import load_daily_cache
from quant_system.data.csv_source import read_ohlcv_csv
from quant_system.data.universe import read_universe


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
            frame = load_daily_cache(cache_dir, stock.symbol).copy()
            for column in ("name", "market", "board", "industry", "sector"):
                value = getattr(stock, column)
                if value and column not in frame.columns:
                    frame[column] = value
            frames.append(frame)
        except FileNotFoundError:
            missing.append(stock.symbol)

    if strict and missing:
        raise FileNotFoundError(f"Missing cached OHLCV data for symbols: {', '.join(missing[:20])}")

    if not frames:
        raise FileNotFoundError(f"No cached OHLCV data found. Missing symbols: {missing}")

    data = pd.concat(frames, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)
    return data
