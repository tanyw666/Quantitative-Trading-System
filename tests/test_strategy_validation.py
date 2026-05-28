from pathlib import Path

import pandas as pd

from quant_system.optimizer.strategy_validation import validate_strategy_config, validate_strategy_directory


def sample_frame():
    dates = pd.date_range("2024-01-01", periods=25)
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": ["000001"] * 25,
            "open": list(range(10, 35)),
            "high": list(range(11, 36)),
            "low": list(range(9, 34)),
            "close": list(range(10, 35)),
            "volume": [1000] * 24 + [3000],
        }
    )


def test_validate_strategy_config_runs_smoke_screen(tmp_path: Path):
    path = tmp_path / "strategy.yaml"
    path.write_text(
        """
name: tuned
strategy: strong_stock_screen
params:
  min_20d_return: 0.1
  min_volume_ratio: 1.2
  max_atr_pct: 0.2
""",
        encoding="utf-8",
    )

    result = validate_strategy_config(path, frame=sample_frame())

    assert result.ok
    assert result.strategy_type == "StrongStockScreen"
    assert result.smoke["rows"] == 1


def test_validate_strategy_config_warns_unknown_score_weight(tmp_path: Path):
    path = tmp_path / "strategy.yaml"
    path.write_text(
        """
name: tuned
strategy: strong_stock_screen
scoring_weights:
  unknown_factor: 1.0
""",
        encoding="utf-8",
    )

    result = validate_strategy_config(path)

    assert result.ok
    assert result.warnings


def test_validate_strategy_config_reports_bad_config(tmp_path: Path):
    path = tmp_path / "strategy.yaml"
    path.write_text("name: broken\n", encoding="utf-8")

    result = validate_strategy_config(path)

    assert not result.ok
    assert result.errors


def test_validate_strategy_directory_checks_yaml_files(tmp_path: Path):
    (tmp_path / "one.yaml").write_text(
        """
name: one
strategy: strong_stock_screen
""",
        encoding="utf-8",
    )
    (tmp_path / "two.yml").write_text(
        """
name: two
strategy: trend_breakout
""",
        encoding="utf-8",
    )

    results = validate_strategy_directory(tmp_path)

    assert len(results) == 2
    assert all(result.ok for result in results)
