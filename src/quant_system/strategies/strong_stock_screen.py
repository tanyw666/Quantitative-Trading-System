from __future__ import annotations

import pandas as pd

from quant_system.factors.technical import add_core_factors
from quant_system.screening.scoring import score_candidates


class StrongStockScreen:
    name = "strong_stock_screen"

    def __init__(
        self,
        min_20d_return: float = 0.12,
        min_volume_ratio: float = 1.5,
        max_atr_pct: float = 0.12,
    ) -> None:
        self.min_20d_return = min_20d_return
        self.min_volume_ratio = min_volume_ratio
        self.max_atr_pct = max_atr_pct

    def generate_signals(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = add_core_factors(frame)
        data["buy_signal"] = (
            (data["momentum_20"] >= self.min_20d_return)
            & (data["volume_ratio_20"] >= self.min_volume_ratio)
            & (data["atr_pct_14"] <= self.max_atr_pct)
            & (data["close"] >= data["ma20"])
        )
        data["sell_signal"] = False
        return data

    def screen(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = self.generate_signals(frame)
        latest = data.groupby("symbol").tail(1) if "symbol" in data.columns else data.tail(1)
        selected = latest[latest["buy_signal"]].copy()
        sort_by = "momentum_20" if "momentum_20" in selected.columns else "close"
        selected = selected.sort_values(sort_by, ascending=False)
        if not selected.empty:
            selected["reason"] = "20日涨幅、量比、波动率和均线位置同时达标"
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
