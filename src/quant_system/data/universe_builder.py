from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

CODE = "\u8bc1\u5238\u4ee3\u7801"
NAME = "\u8bc1\u5238\u7b80\u79f0"
STOCK_NAME = "\u80a1\u7968\u7b80\u79f0"
A_SHARE_NAME = "A\u80a1\u7b80\u79f0"
LISTING_DATE = "\u4e0a\u5e02\u65e5\u671f"
LISTING_TIME = "\u4e0a\u5e02\u65f6\u95f4"
INDUSTRY = "\u6240\u5c5e\u884c\u4e1a"
BOARD = "\u677f\u5757"
CONCEPT = "\u6982\u5ff5"


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

    try:
        raw = ak.stock_info_a_code_name()
    except Exception as exc:
        raise RuntimeError("Unable to load a real A-share universe from AkShare") from exc

    try:
        bj = ak.stock_info_bj_name_code()
        if bj is not None and not bj.empty:
            bj = _normalize_source_columns(
                bj,
                code_candidates=["code", CODE, "代码", "股票代码"],
                name_candidates=["name", NAME, STOCK_NAME, A_SHARE_NAME, "名称", "股票名称"],
                listing_date_candidates=["listing_date", LISTING_DATE, LISTING_TIME],
                industry_candidates=["industry", INDUSTRY, "\u884c\u4e1a"],
            )
            keep = [column for column in ("code", "name", "listing_date", "industry") if column in bj.columns]
            if keep:
                raw = pd.concat([raw, bj[keep]], ignore_index=True, sort=False)
    except Exception:
        pass

    normalized = normalize_universe(raw)
    return normalized.drop_duplicates(subset=["symbol"]).reset_index(drop=True)


def normalize_universe(frame: pd.DataFrame) -> pd.DataFrame:
    data = _normalize_source_columns(
        frame,
        code_candidates=["symbol", "code", CODE, "代码", "股票代码"],
        name_candidates=["name", NAME, STOCK_NAME, A_SHARE_NAME, "名称", "股票名称"],
        listing_date_candidates=["listing_date", LISTING_DATE, LISTING_TIME, f"{LISTING_DATE} "],
        industry_candidates=["industry", INDUSTRY, "\u884c\u4e1a"],
        sector_candidates=["sector", BOARD, CONCEPT],
    )

    if "symbol" not in data.columns or "name" not in data.columns:
        raise ValueError("Universe source must contain symbol/code and name columns")

    result = pd.DataFrame()
    result["symbol"] = data["symbol"].astype(str).str.strip().str.zfill(6)
    result["name"] = data["name"].astype(str).str.strip()
    result["market"] = result["symbol"].apply(infer_market)
    result["board"] = result["symbol"].apply(infer_board)
    result["is_st"] = result["name"].str.upper().str.contains("ST", regex=False)
    result["listing_date"] = _normalize_date_column(data)
    result["industry"] = _normalize_text_column(data, ["industry", INDUSTRY, "\u884c\u4e1a"])
    result["sector"] = _normalize_text_column(data, ["sector", BOARD, CONCEPT])
    return result[["symbol", "name", "market", "board", "is_st", "industry", "sector", "listing_date"]]


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
    if code.startswith(("4", "8", "9", "920")):
        return "BJ"
    return "UNKNOWN"


def infer_board(symbol: str) -> str:
    code = str(symbol).zfill(6)
    if code.startswith(("688", "689")):
        return "STAR"
    if code.startswith(("300", "301")):
        return "CHINEXT"
    if code.startswith(("4", "8", "9", "920")):
        return "BSE"
    return "MAIN"


def _normalize_text_column(frame: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for column in candidates:
        if column in frame.columns:
            return frame[column].fillna("").astype(str).str.strip()
    return pd.Series([""] * len(frame), index=frame.index)


def _normalize_date_column(frame: pd.DataFrame) -> pd.Series:
    for column in ("listing_date", LISTING_DATE, LISTING_TIME):
        if column in frame.columns:
            return pd.to_datetime(frame[column], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    return pd.Series([""] * len(frame), index=frame.index)


def _normalize_source_columns(
    frame: pd.DataFrame,
    *,
    code_candidates: list[str] | None = None,
    name_candidates: list[str] | None = None,
    listing_date_candidates: list[str] | None = None,
    industry_candidates: list[str] | None = None,
    sector_candidates: list[str] | None = None,
) -> pd.DataFrame:
    data = frame.copy()
    candidate_groups = {
        "symbol": code_candidates or [],
        "name": name_candidates or [],
        "listing_date": listing_date_candidates or [],
        "industry": industry_candidates or [],
        "sector": sector_candidates or [],
    }
    for target, candidates in candidate_groups.items():
        if target in data.columns:
            continue
        for candidate in candidates:
            if candidate in data.columns:
                data = data.rename(columns={candidate: target})
                break
    return data
