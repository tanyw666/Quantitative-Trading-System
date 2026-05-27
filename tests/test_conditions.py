import pandas as pd

from quant_system.strategies.conditions import evaluate_condition


def test_condition_tree_supports_and_field_comparison():
    row = pd.Series({"close": 12, "ma20": 10, "momentum_20": 0.15})
    result = evaluate_condition(
        row,
        {
            "all": [
                {"field": "close", "op": "gte", "field_right": "ma20"},
                {"field": "momentum_20", "op": "gte", "value": 0.12},
            ]
        },
    )

    assert result.passed
    assert "AND" in result.reason
