from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quant_system.data.csv_source import read_ohlcv_csv
from quant_system.storage.jsonl import read_jsonl


@dataclass(frozen=True)
class ForwardReturnResult:
    date: str
    symbol: str
    strategy: str
    close: float
    horizon: int
    future_close: float | None
    forward_return: float | None
    entry_gate: str = ""
    dragon_state: str = ""
    dragon_tags: str = ""
    dragon_score: float = 0.0
    seal_quality_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "close": self.close,
            "horizon": self.horizon,
            "future_close": self.future_close,
            "forward_return": self.forward_return,
            "entry_gate": self.entry_gate,
            "dragon_state": self.dragon_state,
            "dragon_tags": self.dragon_tags,
            "dragon_score": self.dragon_score,
            "seal_quality_score": self.seal_quality_score,
        }


def validate_selection_file(
    tracker_path: Path,
    price_csv: Path,
    horizons: tuple[int, ...] = (1, 3, 5),
) -> pd.DataFrame:
    selections = read_jsonl(tracker_path)
    prices = read_ohlcv_csv(price_csv)
    results = validate_selections(selections, prices, horizons)
    return pd.DataFrame([result.to_dict() for result in results])


def validate_selections(
    selections: list[dict],
    prices: pd.DataFrame,
    horizons: tuple[int, ...] = (1, 3, 5),
) -> list[ForwardReturnResult]:
    if not selections:
        return []

    data = prices.copy()
    if "symbol" not in data.columns:
        data["symbol"] = "SINGLE"
    data["date"] = pd.to_datetime(data["date"])
    data["symbol"] = data["symbol"].astype(str).str.zfill(6)

    results: list[ForwardReturnResult] = []
    for selection in selections:
        symbol = str(selection.get("symbol", "SINGLE")).zfill(6)
        selected_at = pd.to_datetime(selection["date"])
        strategy = str(selection.get("strategy", ""))
        entry_gate = str(selection.get("entry_gate", ""))
        dragon_state = str(selection.get("dragon_state", ""))
        dragon_tags = str(selection.get("dragon_tags", ""))
        dragon_score = float(selection.get("dragon_score", 0.0) or 0.0)
        seal_quality_score = float(selection.get("seal_quality_score", 0.0) or 0.0)

        symbol_prices = data[data["symbol"] == symbol].sort_values("date").reset_index(drop=True)
        if symbol_prices.empty:
            continue

        base_candidates = symbol_prices[symbol_prices["date"] >= selected_at]
        if base_candidates.empty:
            continue

        base_index = int(base_candidates.index[0])
        base_close = float(symbol_prices.loc[base_index, "close"])
        for horizon in horizons:
            future_index = base_index + horizon
            if future_index >= len(symbol_prices):
                future_close = None
                forward_return = None
            else:
                future_close = float(symbol_prices.loc[future_index, "close"])
                forward_return = future_close / base_close - 1.0
            results.append(
                ForwardReturnResult(
                    date=selected_at.strftime("%Y-%m-%d"),
                    symbol=symbol,
                    strategy=strategy,
                    close=base_close,
                    horizon=horizon,
                    future_close=future_close,
                    forward_return=forward_return,
                    entry_gate=entry_gate,
                    dragon_state=dragon_state,
                    dragon_tags=dragon_tags,
                    dragon_score=dragon_score,
                    seal_quality_score=seal_quality_score,
                )
            )

    return results


def summarize_forward_returns(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame(columns=["horizon", "count", "mean_return", "win_rate"])

    valid = results.dropna(subset=["forward_return"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=["horizon", "count", "mean_return", "win_rate"])

    summary = valid.groupby("horizon").agg(
        count=("forward_return", "count"),
        mean_return=("forward_return", "mean"),
        win_rate=("forward_return", lambda item: float((item > 0).mean())),
    )
    return summary.reset_index()


def summarize_forward_returns_by(results: pd.DataFrame, group_column: str) -> pd.DataFrame:
    if results.empty or group_column not in results.columns:
        return pd.DataFrame(columns=[group_column, "horizon", "count", "mean_return", "win_rate"])

    valid = results.dropna(subset=["forward_return"]).copy()
    valid[group_column] = valid[group_column].fillna("").astype(str)
    valid = valid[valid[group_column] != ""]
    if valid.empty:
        return pd.DataFrame(columns=[group_column, "horizon", "count", "mean_return", "win_rate"])

    summary = valid.groupby([group_column, "horizon"]).agg(
        count=("forward_return", "count"),
        mean_return=("forward_return", "mean"),
        win_rate=("forward_return", lambda item: float((item > 0).mean())),
    )
    return summary.reset_index().sort_values([group_column, "horizon"]).reset_index(drop=True)
