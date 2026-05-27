from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant_system.data.providers import fetch_with_fallback
from quant_system.storage.frame_cache import read_frame_cache, write_frame_cache


def symbol_cache_path(cache_dir: Path, symbol: str) -> Path:
    normalized = symbol.strip().lower()
    return cache_dir / normalized


def load_daily_cache(cache_dir: Path, symbol: str) -> pd.DataFrame:
    path = symbol_cache_path(cache_dir, symbol)
    return read_frame_cache(path)


def save_daily_cache(cache_dir: Path, symbol: str, frame: pd.DataFrame) -> Path:
    path = symbol_cache_path(cache_dir, symbol)
    return write_frame_cache(frame, path).path


def fetch_daily_to_cache(
    symbol: str,
    start_date: str,
    end_date: str,
    cache_dir: Path,
    adjust: str = "qfq",
    source: str = "auto",
) -> Path:
    result = fetch_with_fallback(symbol=symbol, start=start_date, end=end_date, adjust=adjust, source=source)
    frame = result.frame
    return save_daily_cache(cache_dir, symbol, frame)
