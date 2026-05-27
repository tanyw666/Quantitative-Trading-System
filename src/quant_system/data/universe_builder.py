from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class UniverseBuildOptions:
    include_st: bool = False
    include_bj: bool = False
    include_star: bool = True
    include_chinext: bool = True
    min_list_days: int | None = None


def fetch_akshare_universe() -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise RuntimeError("AkShare is not installed. Run: python -m pip install -e .[data]") from exc

    raw = ak.stock_zh_a_spot_em()
    return normalize_universe(raw)


def normalize_universe(frame: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "代码": "symbol",
        "名称": "name",
        "上市日期": "listing_date",
        "行业": "industry",
        "所属行业": "industry",
        "symbol": "symbol",
        "code": "symbol",
        "name": "name",
        "listing_date": "listing_date",
        "industry": "industry",
        "sector": "sector",
    }
    data = frame.rename(columns=rename_map).copy()
    if "symbol" not in data.columns or "name" not in data.columns:
        raise ValueError("Universe source must contain symbol/code and name columns")

    data["symbol"] = data["symbol"].astype(str).str.strip().str.zfill(6)
    data["name"] = data["name"].astype(str).str.strip()
    data["market"] = data["symbol"].apply(infer_market)
    data["board"] = data["symbol"].apply(infer_board)
    data["is_st"] = data["name"].str.upper().str.contains("ST", regex=False)
    if "listing_date" in data.columns:
        data["listing_date"] = pd.to_datetime(data["listing_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    optional = [column for column in ("industry", "sector", "listing_date") if column in data.columns]
    return data[["symbol", "name", "market", "board", "is_st"] + optional]


def filter_universe(frame: pd.DataFrame, options: UniverseBuildOptions, as_of: date | None = None) -> pd.DataFrame:
    data = normalize_universe(frame) if not {"symbol", "name", "market", "board", "is_st"}.issubset(frame.columns) else frame.copy()
    if not options.include_st:
        data = data[~data["is_st"]]
    if not options.include_bj:
        data = data[data["market"] != "BJ"]
    if not options.include_star:
        data = data[data["board"] != "STAR"]
    if not options.include_chinext:
        data = data[data["board"] != "CHINEXT"]
    if options.min_list_days is not None and "listing_date" in data.columns:
        as_of_date = pd.Timestamp(as_of or date.today())
        listing = pd.to_datetime(data["listing_date"], errors="coerce")
        age_days = (as_of_date - listing).dt.days
        data = data[(age_days.isna()) | (age_days >= options.min_list_days)]
    return data.sort_values("symbol").reset_index(drop=True)


def save_universe(frame: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8")
    return path


def infer_market(symbol: str) -> str:
    code = str(symbol).zfill(6)
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return "SH"
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZ"
    if code.startswith(("4", "8", "9")):
        return "BJ"
    return "UNKNOWN"


def infer_board(symbol: str) -> str:
    code = str(symbol).zfill(6)
    if code.startswith(("688", "689")):
        return "STAR"
    if code.startswith(("300", "301")):
        return "CHINEXT"
    if code.startswith(("4", "8", "9")):
        return "BSE"
    return "MAIN"
