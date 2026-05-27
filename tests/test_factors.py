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
