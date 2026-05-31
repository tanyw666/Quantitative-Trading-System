from __future__ import annotations

import pandas as pd

from quant_system.factors.technical import add_core_factors
from quant_system.screening.scoring import score_candidates
from quant_system.screening.value_filters import add_value_filter_fields


class SteadyReversalSharpeStrategy:
    name = "steady_reversal_sharpe"

    def __init__(
        self,
        min_like_sharpe: float = 1.0,
        holding_count: int = 5,
        rebalance_period: int = 20,
        min_traded_value: float = 0.0,
        max_atr_pct: float = 0.20,
        require_value_pass: bool = True,
        require_turnover: bool = True,
    ) -> None:
        self.min_like_sharpe = min_like_sharpe
        self.holding_count = holding_count
        self.rebalance_period = rebalance_period
        self.min_traded_value = min_traded_value
        self.max_atr_pct = max_atr_pct
        self.require_value_pass = require_value_pass
        self.require_turnover = require_turnover

    def generate_signals(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = add_value_filter_fields(add_core_factors(frame))
        data = data.sort_values(["date", "symbol"] if "symbol" in data.columns else ["date"]).copy()
        if "symbol" not in data.columns:
            data["symbol"] = "SINGLE"

        data["buy_signal"] = False
        data["sell_signal"] = False
        dates = list(pd.Series(pd.to_datetime(data["date"]).drop_duplicates()).sort_values())
        rebalance_dates = {
            date
            for index, date in enumerate(dates)
            if index % max(int(self.rebalance_period), 1) == 0
        }
        data["_rebalance_date"] = pd.to_datetime(data["date"]).isin(rebalance_dates)

        for date, day in data.groupby("date", sort=True):
            if not bool(day["_rebalance_date"].iloc[0]):
                continue
            selected_symbols = set(self._select_from_day(day)["symbol"].astype(str))
            data.loc[day.index, "buy_signal"] = day["symbol"].astype(str).isin(selected_symbols)
            data.loc[day.index, "sell_signal"] = ~day["symbol"].astype(str).isin(selected_symbols)

        data = data.drop(columns=["_rebalance_date"])
        return data

    def screen(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = add_value_filter_fields(add_core_factors(frame))
        if "symbol" not in data.columns:
            data["symbol"] = "SINGLE"
        latest = data.groupby("symbol").tail(1)
        selected = self._select_from_day(latest)
        if not selected.empty:
            selected["reason"] = "like_sharpe_10 above threshold, then ranked by low turnover and low amplitude reversal score"
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
                "like_sharpe_10",
                "return_10",
                "return_volatility_10",
                "turnover_60_avg",
                "amplitude_10_avg",
                "low_turnover_z",
                "low_amplitude_z",
                "steady_reversal_score",
                "traded_value",
                "atr_pct_14",
                "value_filter_status",
                "value_filter_reason",
                "reason",
            )
            if col in selected.columns
        ]
        return selected[columns].reset_index(drop=True)

    def _select_from_day(self, day: pd.DataFrame) -> pd.DataFrame:
        selected = day.copy()
        selected = selected[
            pd.to_numeric(selected["like_sharpe_10"], errors="coerce").fillna(float("-inf")) > self.min_like_sharpe
        ]
        selected = selected[
            pd.to_numeric(selected["steady_reversal_score"], errors="coerce").notna()
        ]
        if self.require_turnover:
            selected = selected[pd.to_numeric(selected["turnover_60_avg"], errors="coerce").notna()]
        if "traded_value" in selected.columns:
            selected = selected[pd.to_numeric(selected["traded_value"], errors="coerce").fillna(0.0) >= self.min_traded_value]
        if "atr_pct_14" in selected.columns:
            selected = selected[pd.to_numeric(selected["atr_pct_14"], errors="coerce").fillna(float("inf")) <= self.max_atr_pct]
        if self.require_value_pass and "value_filter_status" in selected.columns:
            selected = selected[selected["value_filter_status"] != "block"]
        selected = selected.sort_values(
            ["steady_reversal_score", "like_sharpe_10"],
            ascending=[False, False],
        )
        return selected.head(max(int(self.holding_count), 0)).copy()
