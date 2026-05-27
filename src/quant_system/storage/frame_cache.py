from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CacheWriteResult:
    path: Path
    format: str


def _normalize_for_disk(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"]).dt.strftime("%Y-%m-%d")
    if "symbol" in data.columns:
        data["symbol"] = data["symbol"].astype(str).str.strip().str.zfill(6)
    return data


def write_frame_cache(frame: pd.DataFrame, path_without_suffix: Path, prefer: str = "parquet") -> CacheWriteResult:
    """Write a DataFrame cache, preferring Parquet but falling back to CSV."""
    path_without_suffix.parent.mkdir(parents=True, exist_ok=True)
    data = _normalize_for_disk(frame)

    if prefer == "parquet":
        parquet_path = path_without_suffix.with_suffix(".parquet")
        try:
            data.to_parquet(parquet_path, index=False)
            return CacheWriteResult(parquet_path, "parquet")
        except (ImportError, ModuleNotFoundError, ValueError):
            pass

    csv_path = path_without_suffix.with_suffix(".csv")
    data.to_csv(csv_path, index=False, encoding="utf-8")
    return CacheWriteResult(csv_path, "csv")


def read_frame_cache(path_without_suffix: Path) -> pd.DataFrame:
    parquet_path = path_without_suffix.with_suffix(".parquet")
    csv_path = path_without_suffix.with_suffix(".csv")

    if parquet_path.exists():
        data = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        data = pd.read_csv(csv_path, dtype={"symbol": str})
    else:
        raise FileNotFoundError(f"No cache found for {path_without_suffix}")

    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"])
    if "symbol" in data.columns:
        data["symbol"] = data["symbol"].astype(str).str.strip().str.zfill(6)
    return data
