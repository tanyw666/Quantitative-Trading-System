from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Protocol

import pandas as pd


class DailyBarProvider(Protocol):
    name: str

    def fetch_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        ...


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    frame: pd.DataFrame


def normalize_daily_bars(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    rename_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "换手率": "turnover",
        "date": "date",
        "open": "open",
        "close": "close",
        "high": "high",
        "low": "low",
        "volume": "volume",
        "amount": "amount",
        "turnover": "turnover",
    }
    data = frame.rename(columns=rename_map).copy()
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Provider returned missing columns: {missing}")

    data["symbol"] = str(symbol).zfill(6)
    data["date"] = pd.to_datetime(data["date"])
    for column in ["open", "high", "low", "close", "volume"]:
        data[column] = pd.to_numeric(data[column], errors="raise")
    return data.sort_values("date").reset_index(drop=True)


class AkShareDailyProvider:
    name = "akshare"

    def fetch_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        try:
            import akshare as ak  # type: ignore
        except ImportError as exc:
            raise RuntimeError("AkShare is not installed. Run: python -m pip install -e .[data]") from exc

        raw = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start,
            end_date=end,
            adjust=adjust,
        )
        return normalize_daily_bars(raw, symbol)


class MootdxDailyProvider:
    name = "mootdx"

    def fetch_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        raise RuntimeError(
            "mootdx provider is reserved but not enabled yet. "
            "Use source=akshare or source=auto until mootdx connection parameters are configured."
        )


def provider_chain(source: str = "auto") -> list[DailyBarProvider]:
    normalized = source.strip().lower()
    if normalized == "auto":
        return [MootdxDailyProvider(), AkShareDailyProvider()]
    if normalized == "mootdx":
        return [MootdxDailyProvider()]
    if normalized == "akshare":
        return [AkShareDailyProvider()]
    raise ValueError(f"Unknown data source: {source}")


def fetch_with_fallback(
    symbol: str,
    start: str,
    end: str,
    adjust: str,
    source: str = "auto",
    attempts: int = 2,
    retry_sleep: float = 0.5,
) -> ProviderResult:
    errors: list[str] = []
    for provider in provider_chain(source):
        for attempt in range(1, max(attempts, 1) + 1):
            try:
                frame = provider.fetch_daily(symbol=symbol, start=start, end=end, adjust=adjust)
                if not frame.empty:
                    return ProviderResult(provider=provider.name, frame=frame)
                errors.append(f"{provider.name} attempt {attempt}: empty result")
            except Exception as exc:  # noqa: BLE001 - keep fallback chain alive.
                errors.append(f"{provider.name} attempt {attempt}: {exc}")
            if attempt < attempts:
                sleep(retry_sleep)
    raise RuntimeError(f"All data providers failed for {symbol}: {' | '.join(errors)}")
