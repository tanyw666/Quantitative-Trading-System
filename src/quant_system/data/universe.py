from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class StockInfo:
    symbol: str
    name: str = ""
    market: str = "A"
    board: str = ""
    industry: str = ""
    sector: str = ""


def read_universe(path: Path) -> list[StockInfo]:
    frame = pd.read_csv(path, dtype={"symbol": str, "code": str})
    if "symbol" not in frame.columns and "code" in frame.columns:
        frame = frame.rename(columns={"code": "symbol"})
    if "symbol" not in frame.columns:
        raise ValueError("Universe CSV must contain a symbol or code column")

    stocks: list[StockInfo] = []
    for row in frame.to_dict(orient="records"):
        symbol = _clean_symbol(row.get("symbol", ""))
        if not symbol:
            continue
        stocks.append(
            StockInfo(
                symbol=symbol,
                name=_clean_text(row.get("name", "")),
                market=_clean_text(row.get("market", "A"), default="A"),
                board=_clean_text(row.get("board", "")),
                industry=_clean_text(row.get("industry", "")),
                sector=_clean_text(row.get("sector", "")),
            )
        )
    return stocks


def _clean_text(value: object, default: str = "") -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _clean_symbol(value: object) -> str:
    text = _clean_text(value)
    if text.isdigit() and len(text) < 6:
        return text.zfill(6)
    return text
