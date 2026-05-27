from __future__ import annotations

import pandas as pd

from quant_system.factors.technical import add_core_factors
from quant_system.screening.scoring import score_candidates


class TrendBreakoutStrategy:
    name = "trend_breakout"

    def __init__(self, min_momentum: float = 0.03) -> None:
        self.min_momentum = min_momentum

    def generate_signals(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = add_core_factors(frame)
        data["buy_signal"] = (
            (data["close"] > data["rolling_high_20"])
            & (data["ma5"] > data["ma20"])
            & (data["momentum_20"] >= self.min_momentum)
        )
        data["sell_signal"] = data["ma5"] < data["ma20"]
        return data

    def screen(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = self.generate_signals(frame)
        latest = data.groupby("symbol").tail(1) if "symbol" in data.columns else data.tail(1)
        selected = latest[latest["buy_signal"]].copy()
        if not selected.empty:
            selected["reason"] = "突破前20日高点，MA5高于MA20，20日动量达标"
        selected = score_candidates(selected)
        columns = [
            col
            for col in (
                "date",
                "symbol",
                "name",
                "market",
                "board",
                "industry",
                "sector",
                "close",
                "score",
                "risk_grade",
                "atr_stop_price",
                "momentum_20",
                "volume_ratio_20",
                "atr_14",
                "atr_pct_14",
            )
            if col in selected.columns
        ]
        if "reason" in selected.columns:
            columns.append("reason")
        return selected[columns].reset_index(drop=True)
