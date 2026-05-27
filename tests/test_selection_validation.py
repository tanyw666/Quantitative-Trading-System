import pandas as pd

from quant_system.optimizer.selection_validation import (
    summarize_forward_returns,
    summarize_forward_returns_by,
    validate_selections,
)


def test_validate_selections_calculates_forward_returns():
    prices = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=6),
            "symbol": ["000001"] * 6,
            "open": [10, 11, 12, 13, 14, 15],
            "high": [10, 11, 12, 13, 14, 15],
            "low": [10, 11, 12, 13, 14, 15],
            "close": [10, 11, 12, 13, 14, 15],
            "volume": [1000] * 6,
        }
    )
    selections = [
        {
            "date": "2024-01-01",
            "symbol": "000001",
            "strategy": "demo",
            "close": 10,
            "entry_gate": "pass",
            "dragon_state": "sealed",
            "dragon_tags": "reseal-candidate",
            "dragon_score": 100,
            "seal_quality_score": 90,
        }
    ]

    results = validate_selections(selections, prices, horizons=(1, 3, 5))
    result_frame = pd.DataFrame([item.to_dict() for item in results])
    summary = summarize_forward_returns(result_frame)
    gate_summary = summarize_forward_returns_by(result_frame, "entry_gate")

    assert abs(results[0].forward_return - 0.1) < 1e-12
    assert abs(results[1].forward_return - 0.3) < 1e-12
    assert results[0].entry_gate == "pass"
    assert results[0].dragon_state == "sealed"
    assert summary.loc[summary["horizon"] == 1, "win_rate"].iloc[0] == 1.0
    assert gate_summary.loc[0, "entry_gate"] == "pass"
