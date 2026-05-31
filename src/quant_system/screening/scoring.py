from __future__ import annotations

import pandas as pd

from quant_system.config.settings import DEFAULT_SCORING_WEIGHTS
from quant_system.screening.value_filters import add_value_filter_fields

SUPPORTED_SCORE_COLUMNS = (
    "momentum_20",
    "volume_ratio_20",
    "atr_pct_14",
    "sector_strength_score",
    "ma20_slope_5",
    "close_to_ma20",
    "traded_value",
    "rsi_14",
    "trend_quality_score",
    "entry_structure_score",
    "chase_risk_score",
    "candle_warning_count",
    "tape_pressure_score",
    "tape_distribution_warning",
    "volume_confirmation_score",
    "candle_quality_score",
    "breakout_quality_score",
    "false_breakout_pressure",
    "like_sharpe_10",
    "steady_reversal_score",
    "turnover_60_avg",
    "amplitude_10_avg",
)


def score_candidates(frame: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    weights = weights or DEFAULT_SCORING_WEIGHTS
    scored = add_value_filter_fields(frame)
    scored["score"] = 0.0

    rules: list[tuple[str, float, bool]] = [
        (SUPPORTED_SCORE_COLUMNS[0], float(weights.get("momentum_20", 0.50)), True),
        (SUPPORTED_SCORE_COLUMNS[1], float(weights.get("volume_ratio_20", 0.30)), True),
        (SUPPORTED_SCORE_COLUMNS[2], float(weights.get("atr_pct_14", 0.20)), False),
        (SUPPORTED_SCORE_COLUMNS[3], float(weights.get("sector_strength_score", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[4], float(weights.get("ma20_slope_5", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[5], float(weights.get("close_to_ma20", 0.0)), False),
        (SUPPORTED_SCORE_COLUMNS[6], float(weights.get("traded_value", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[7], float(weights.get("rsi_14", 0.0)), False),
        (SUPPORTED_SCORE_COLUMNS[8], float(weights.get("trend_quality_score", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[9], float(weights.get("entry_structure_score", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[10], float(weights.get("chase_risk_score", 0.0)), False),
        (SUPPORTED_SCORE_COLUMNS[11], float(weights.get("candle_warning_count", 0.0)), False),
        (SUPPORTED_SCORE_COLUMNS[12], float(weights.get("tape_pressure_score", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[13], float(weights.get("tape_distribution_warning", 0.0)), False),
        (SUPPORTED_SCORE_COLUMNS[14], float(weights.get("volume_confirmation_score", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[15], float(weights.get("candle_quality_score", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[16], float(weights.get("breakout_quality_score", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[17], float(weights.get("false_breakout_pressure", 0.0)), False),
        (SUPPORTED_SCORE_COLUMNS[18], float(weights.get("like_sharpe_10", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[19], float(weights.get("steady_reversal_score", 0.0)), True),
        (SUPPORTED_SCORE_COLUMNS[20], float(weights.get("turnover_60_avg", 0.0)), False),
        (SUPPORTED_SCORE_COLUMNS[21], float(weights.get("amplitude_10_avg", 0.0)), False),
    ]

    used_weight = 0.0
    for column, weight, higher_is_better in rules:
        if column not in scored.columns:
            continue
        values = pd.to_numeric(scored[column], errors="coerce")
        rank_source = values if higher_is_better else -values
        ranks = rank_source.rank(pct=True).fillna(0.0)
        scored["score"] += ranks * weight
        used_weight += weight

    if used_weight:
        scored["score"] = scored["score"] / used_weight * 100
    else:
        scored["score"] = 0.0

    if "atr_pct_14" in scored.columns:
        scored["risk_grade"] = scored["atr_pct_14"].apply(_risk_grade)
    else:
        scored["risk_grade"] = "unknown"

    if {"close", "atr_14"}.issubset(scored.columns):
        scored["atr_stop_price"] = (scored["close"] - 2 * scored["atr_14"]).clip(lower=0)

    sort_columns = ["score"]
    ascending = [False]
    if "momentum_20" in scored.columns:
        sort_columns.append("momentum_20")
        ascending.append(False)
    if "sector_strength_score" in scored.columns:
        sort_columns.append("sector_strength_score")
        ascending.append(False)
    if "entry_structure_score" in scored.columns:
        sort_columns.append("entry_structure_score")
        ascending.append(False)
    return scored.sort_values(sort_columns, ascending=ascending).reset_index(drop=True)


def _risk_grade(atr_pct: float) -> str:
    if pd.isna(atr_pct):
        return "unknown"
    if atr_pct <= 0.04:
        return "low"
    if atr_pct <= 0.08:
        return "medium"
    return "high"
