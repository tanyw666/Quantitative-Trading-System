import pandas as pd

from quant_system.backtest.engine import BacktestConfig
from quant_system.optimizer.parameter_calibration import (
    render_calibration_markdown,
    run_structure_parameter_calibration,
)


def _sample_frame():
    dates = pd.date_range("2024-01-01", periods=35)
    closes = list(range(10, 44)) + [45]
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": ["000001"] * 35,
            "name": ["Demo"] * 35,
            "open": [value - 0.2 for value in closes],
            "high": [value + 0.5 for value in closes],
            "low": [value - 0.5 for value in closes],
            "close": closes,
            "volume": [1000] * 34 + [2500],
        }
    )


def test_structure_parameter_calibration_ranks_cases_and_renders_markdown():
    summary = run_structure_parameter_calibration(
        _sample_frame(),
        grid=[
            {"min_entry_structure_score": 0, "max_chase_risk_score": 100, "max_candle_warning_count": 1, "block_false_breakout": True},
            {"min_entry_structure_score": 95, "max_chase_risk_score": 10, "max_candle_warning_count": 0, "block_false_breakout": True},
        ],
        base_params={"min_20d_return": 0.1, "min_volume_ratio": 1.2, "max_atr_pct": 0.3},
        backtest_config=BacktestConfig(initial_cash=100000, max_position_pct=0.2, commission_rate=0, slippage_rate=0),
    )

    assert summary["case_count"] == 2
    assert summary["best"]["signal_count"] >= 0
    assert summary["cases"]
    assert "min_entry_structure_score" in summary["sensitivity"]
    assert "max_chase_risk_score" in summary["sensitivity"]
    assert "block_false_breakout" in summary["sensitivity"]

    content = render_calibration_markdown(summary)
    assert "# Structure Parameter Calibration" in content
    assert "Threshold Sensitivity" in content
    assert "Top Cases" in content
