from pathlib import Path

import pandas as pd

from quant_system.optimizer.promotion import (
    append_promotion_record,
    promote_strategy_from_summary,
    read_promotion_records,
    summarize_promotion_records,
)


def summary_file(tmp_path: Path) -> Path:
    path = tmp_path / "summary.json"
    path.write_text(
        """
{
  "preferred_horizon": 1,
  "min_count": 1,
  "recommendation": {
    "name": "balanced",
    "strategy": "strong_stock_screen",
    "params": {
      "min_20d_return": 0.1,
      "min_volume_ratio": 1.2,
      "max_atr_pct": 0.2
    },
    "scoring_weights": {
      "momentum_20": 0.8
    },
    "score": 0.03
  },
  "result_count": 1
}
""",
        encoding="utf-8",
    )
    return path


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


def test_promote_strategy_from_summary_writes_and_validates_config(tmp_path: Path):
    output = tmp_path / "promoted.yaml"

    result = promote_strategy_from_summary(summary_file(tmp_path), output, frame=sample_frame())

    assert result.ok
    assert output.exists()
    assert result.created_at
    assert result.summary.endswith("summary.json")
    assert result.output.endswith("promoted.yaml")
    assert result.backtest_requested is False
    assert result.validation["smoke"]["rows"] == 1


def test_promote_strategy_from_summary_can_backtest(tmp_path: Path):
    output = tmp_path / "promoted.yaml"

    result = promote_strategy_from_summary(summary_file(tmp_path), output, frame=sample_frame(), backtest=True)

    assert result.ok
    assert result.backtest_requested is True
    assert "total_return" in result.backtest


def test_append_promotion_record_writes_jsonl(tmp_path: Path):
    output = tmp_path / "promoted.yaml"
    log_path = tmp_path / "promotions.jsonl"
    result = promote_strategy_from_summary(summary_file(tmp_path), output, frame=sample_frame())

    append_promotion_record(log_path, result)
    records = read_promotion_records(log_path)

    assert len(records) == 1
    assert records[0]["created_at"]
    assert records[0]["ok"] is True
    assert records[0]["output"].endswith("promoted.yaml")


def test_summarize_promotion_records_compacts_history(tmp_path: Path):
    output = tmp_path / "promoted.yaml"
    result = promote_strategy_from_summary(summary_file(tmp_path), output, frame=sample_frame(), backtest=True)
    records = [
        {
            **result.to_dict(),
            "output": "old.yaml",
            "backtest": {"total_return": -0.01, "sharpe": -1.0, "trades": 1},
        },
        result.to_dict(),
    ]

    summary = summarize_promotion_records(records, limit=1)

    assert summary["total"] == 2
    assert summary["ok_count"] == 2
    assert summary["failed_count"] == 0
    assert summary["backtest_count"] == 2
    assert summary["best_backtest"]["output"].endswith("promoted.yaml")
    assert len(summary["records"]) == 1
