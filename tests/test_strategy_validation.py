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
    assert result.score == 100.0
    assert result.status == "ok"
    assert result.action == "keep"


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


def test_validate_strategy_config_marks_trade_plan_pressure(tmp_path: Path):
    path = tmp_path / "strategy.yaml"
    path.write_text(
        """
name: tuned
strategy: strong_stock_screen
""",
        encoding="utf-8",
    )

    pressure = {"match_rate": 0.62, "unmatched_plans": 3, "orphan_trades": 2, "avg_price_deviation_pct": 0.05}
    result = validate_strategy_config(path, frame=sample_frame().head(3), trade_plan_pressure=pressure)

    assert result.score < 100
    assert result.status == "warn"
    assert result.action == "reduce"
    assert "trade_plan_mismatch" in result.alerts
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


def test_validate_strategy_directory_applies_trade_plan_pressure(tmp_path: Path):
    (tmp_path / "one.yaml").write_text(
        """
name: one
strategy: strong_stock_screen
""",
        encoding="utf-8",
    )
    pressure = {"match_rate": 0.6, "unmatched_plans": 2, "orphan_trades": 1}

    results = validate_strategy_directory(tmp_path, trade_plan_pressure=pressure)

    assert len(results) == 1
    assert results[0].status == "warn"
    assert results[0].action == "reduce"
