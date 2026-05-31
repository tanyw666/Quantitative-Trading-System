from __future__ import annotations

import pandas as pd

from quant_system.factors.technical import add_core_factors
from quant_system.screening.scoring import score_candidates
from quant_system.screening.value_filters import add_value_filter_fields


class TrendBreakoutStrategy:
    name = "trend_breakout"

    def __init__(
        self,
        min_momentum: float = 0.03,
        min_ma20_slope: float = 0.0,
        max_close_ma20_gap: float = 0.45,
        max_atr_pct: float = 0.16,
        min_traded_value: float = 0.0,
        min_entry_structure_score: float = 0.0,
        max_chase_risk_score: float = 100.0,
        max_candle_warning_count: int = 1,
        block_false_breakout: bool = True,
    ) -> None:
        self.min_momentum = min_momentum
        self.min_ma20_slope = min_ma20_slope
        self.max_close_ma20_gap = max_close_ma20_gap
        self.max_atr_pct = max_atr_pct
        self.min_traded_value = min_traded_value
        self.min_entry_structure_score = min_entry_structure_score
        self.max_chase_risk_score = max_chase_risk_score
        self.max_candle_warning_count = max_candle_warning_count
        self.block_false_breakout = block_false_breakout

    def generate_signals(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = add_value_filter_fields(add_core_factors(frame))
        structure_ok = data["entry_structure_score"].isna() | (data["entry_structure_score"] >= self.min_entry_structure_score)
        chase_ok = data["chase_risk_score"].isna() | (data["chase_risk_score"] <= self.max_chase_risk_score)
        candle_ok = data["candle_warning_count"].fillna(0) <= self.max_candle_warning_count
        false_breakout_ok = (
            ~data["false_breakout_flag"].fillna(False).astype(bool)
            if self.block_false_breakout
            else True
        )
        value_ok = data["value_filter_status"] != "block"
        tape_ok = ~data["tape_distribution_warning"].fillna(False).astype(bool)
        data["buy_signal"] = (
            (data["close"] > data["rolling_high_20"])
            & (data["ma5"] > data["ma20"])
            & (data["momentum_20"] >= self.min_momentum)
            & (data["ma20_slope_5"] >= self.min_ma20_slope)
            & (data["close_to_ma20"] <= self.max_close_ma20_gap)
            & (data["atr_pct_14"] <= self.max_atr_pct)
            & (data["traded_value"] >= self.min_traded_value)
            & structure_ok
            & chase_ok
            & candle_ok
            & false_breakout_ok
            & value_ok
            & tape_ok
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
                "ma20_slope_5",
                "close_to_ma20",
                "close_to_rolling_high_20",
                "traded_value",
                "rsi_14",
                "trend_quality_score",
                "entry_structure_score",
                "chase_risk_score",
                "candle_warning_count",
                "volume_price_state",
                "false_breakout_flag",
                "value_filter_status",
                "value_filter_reason",
                "value_warning_count",
                "tape_pressure_score",
                "tape_distribution_warning",
                "tape_accumulation_hint",
                "volume_confirmation_score",
                "candle_quality_score",
                "breakout_quality_score",
                "false_breakout_pressure",
                "close_position_in_range",
                "upper_shadow_pct",
            )
            if col in selected.columns
        ]
        if "reason" in selected.columns:
            columns.append("reason")
        return selected[columns].reset_index(drop=True)
