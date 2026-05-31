import pandas as pd

from quant_system.factors.technical import add_core_factors, momentum


def test_momentum_uses_past_price_only():
    close = pd.Series([10, 11, 12, 13])
    result = momentum(close, 2)
    assert pd.isna(result.iloc[0])
    assert pd.isna(result.iloc[1])
    assert abs(result.iloc[2] - 0.2) < 1e-12


def test_rolling_high_is_shifted_to_avoid_lookahead():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=25),
            "open": range(1, 26),
            "high": range(1, 26),
            "low": range(1, 26),
            "close": range(1, 26),
            "volume": [1000] * 25,
        }
    )
    enriched = add_core_factors(frame)
    assert enriched.loc[20, "rolling_high_20"] == 20


def test_core_factors_include_trend_quality_and_liquidity_fields():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=30),
            "open": range(10, 40),
            "high": range(11, 41),
            "low": range(9, 39),
            "close": range(10, 40),
            "volume": [1000] * 30,
        }
    )

    enriched = add_core_factors(frame)

    assert "ma20_slope_5" in enriched.columns
    assert "close_to_ma20" in enriched.columns
    assert "traded_value" in enriched.columns
    assert enriched.loc[29, "traded_value"] == 39_000


def test_core_factors_include_book_rule_structure_fields():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=25),
            "open": list(range(10, 34)) + [33],
            "high": list(range(11, 35)) + [36],
            "low": list(range(9, 33)) + [32],
            "close": list(range(10, 34)) + [33.5],
            "volume": [1000] * 24 + [3000],
        }
    )

    enriched = add_core_factors(frame)

    for column in [
        "close_position_in_range",
        "upper_shadow_pct",
        "candle_warning_count",
        "false_breakout_flag",
        "trend_quality_score",
        "entry_structure_score",
        "chase_risk_score",
        "volume_price_state",
        "tape_pressure_score",
        "tape_distribution_warning",
        "tape_accumulation_hint",
        "volume_confirmation_score",
        "candle_quality_score",
        "breakout_quality_score",
        "false_breakout_pressure",
    ]:
        assert column in enriched.columns
    assert enriched.loc[24, "false_breakout_flag"] is True
    assert enriched.loc[24, "false_breakout_pressure"] >= 55
    assert enriched.loc[24, "tape_distribution_warning"] is True
    assert enriched.loc[24, "candle_warning_count"] >= 1
    assert enriched.loc[24, "chase_risk_score"] > 0
