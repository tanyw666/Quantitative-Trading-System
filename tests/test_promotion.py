from pathlib import Path

import pandas as pd

from quant_system.optimizer.promotion import (
    append_promotion_record,
    persist_promotion_record,
    promote_strategy_from_summary,
    read_promotion_records,
    summarize_promotion_records,
)
from quant_system.storage.sqlite_store import SQLiteStore


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
    assert result.strategy_name == "strong_stock_screen_recommended"
    assert result.backtest_requested is False
    assert result.validation["smoke"]["rows"] == 1
    assert "trade_plan_pressure" in result.to_dict()


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


def test_persist_promotion_record_can_dual_write_jsonl_and_sqlite(tmp_path: Path):
    output = tmp_path / "promoted.yaml"
    log_path = tmp_path / "promotions.jsonl"
    sqlite_path = tmp_path / "quant.sqlite"
    result = promote_strategy_from_summary(summary_file(tmp_path), output, frame=sample_frame(), backtest=True)

    persist_promotion_record(log_path, result, sqlite_path=sqlite_path)

    records = read_promotion_records(log_path)
    stored = SQLiteStore(sqlite_path).read_strategy_promotions(limit=1)

    assert len(records) == 1
    assert stored.loc[0, "output_path"].endswith("promoted.yaml")
    assert stored.loc[0, "strategy_name"] == result.strategy_name
    assert stored.loc[0, "total_return"] == result.backtest["total_return"]


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


def test_promotion_summary_compacts_trade_plan_pressure(tmp_path: Path):
    output = tmp_path / "promoted.yaml"
    result = promote_strategy_from_summary(summary_file(tmp_path), output, frame=sample_frame(), backtest=True)
    records = [result.to_dict()]
    records[0]["trade_plan_pressure"] = {"score": 88, "status": "watch", "action": "reduce", "alerts": ["trade_plan_drift"]}

    summary = summarize_promotion_records(records, limit=1)

    assert summary["trade_plan_pressure"]["status"] == "watch"
    assert summary["records"][0]["trade_plan_status"] == "watch"
    assert summary["records"][0]["trade_plan_action"] == "reduce"


def test_promote_strategy_from_summary_accepts_trade_plan_pressure(tmp_path: Path):
    output = tmp_path / "promoted.yaml"
    pressure = {"match_rate": 0.6, "unmatched_plans": 3, "orphan_trades": 2, "avg_price_deviation_pct": 0.05}

    result = promote_strategy_from_summary(
        summary_file(tmp_path),
        output,
        frame=sample_frame(),
        trade_plan_pressure=pressure,
    )

    payload = result.to_dict()
    assert payload["trade_plan_pressure"]["score"] < 100
    assert payload["trade_plan_pressure"]["match_rate"] == 0.6
