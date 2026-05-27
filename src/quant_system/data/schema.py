from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


REQUIRED_OHLCV_COLUMNS = ("date", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class DataQualityReport:
    rows: int
    missing_required: tuple[str, ...]
    duplicated_dates: int
    has_null_prices: bool

    @property
    def ok(self) -> bool:
        return not self.missing_required and self.duplicated_dates == 0 and not self.has_null_prices


def validate_ohlcv(frame: pd.DataFrame) -> DataQualityReport:
    missing = tuple(col for col in REQUIRED_OHLCV_COLUMNS if col not in frame.columns)
    if "date" not in frame.columns:
        duplicated_dates = 0
    elif "symbol" in frame.columns:
        duplicated_dates = int(frame[["symbol", "date"]].duplicated().sum())
    else:
        duplicated_dates = int(frame["date"].duplicated().sum())
    price_columns = [col for col in ("open", "high", "low", "close") if col in frame.columns]
    has_null_prices = bool(frame[price_columns].isna().any().any()) if price_columns else True
    return DataQualityReport(
        rows=len(frame),
        missing_required=missing,
        duplicated_dates=duplicated_dates,
        has_null_prices=has_null_prices,
    )
