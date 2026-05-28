from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from quant_system.backtest.engine import BacktestConfig, BacktestEngine
from quant_system.optimizer.export_strategy import load_experiment_summary, strategy_config_from_summary, write_strategy_config
from quant_system.optimizer.strategy_validation import validate_strategy_config
from quant_system.storage.jsonl import append_jsonl, read_jsonl
from quant_system.strategies.registry import create_strategy_from_config


@dataclass(frozen=True)
class StrategyPromotionResult:
    created_at: str
    summary: str
    output: str
    ok: bool
    backtest_requested: bool
    buy_price_field: str
    cash: float
    validation: dict[str, Any]
    backtest: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "summary": self.summary,
            "output": self.output,
            "ok": self.ok,
            "backtest_requested": self.backtest_requested,
            "buy_price_field": self.buy_price_field,
            "cash": self.cash,
            "validation": self.validation,
            "backtest": self.backtest,
        }


def promote_strategy_from_summary(
    summary_path: Path,
    output_path: Path,
    name: str | None = None,
    description: str | None = None,
    frame: pd.DataFrame | None = None,
    backtest: bool = False,
    buy_price_field: str = "close",
    cash: float = 100000.0,
) -> StrategyPromotionResult:
    summary = load_experiment_summary(summary_path)
    config = strategy_config_from_summary(summary, name=name, description=description)
    write_strategy_config(output_path, config)

    validation = validate_strategy_config(output_path, frame=frame)
    backtest_summary: dict[str, Any] = {}
    if validation.ok and backtest and frame is not None:
        strategy = create_strategy_from_config(output_path)
        backtest_summary = BacktestEngine(
            BacktestConfig(initial_cash=cash, buy_price_field=buy_price_field)
        ).run(frame, strategy).summary()

    return StrategyPromotionResult(
        created_at=datetime.now(timezone.utc).isoformat(),
        summary=str(summary_path),
        output=str(output_path),
        ok=validation.ok,
        backtest_requested=backtest,
        buy_price_field=buy_price_field,
        cash=cash,
        validation=validation.to_dict(),
        backtest=backtest_summary,
    )


def append_promotion_record(path: Path, result: StrategyPromotionResult) -> None:
    append_jsonl(path, result.to_dict())


def read_promotion_records(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def summarize_promotion_records(records: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    visible_records = records[-limit:] if limit > 0 else records
    ok_records = [record for record in records if record.get("ok")]
    failed_records = [record for record in records if not record.get("ok")]
    backtested_records = [record for record in records if record.get("backtest")]

    best_record = _best_backtest_record(backtested_records)
    return {
        "total": len(records),
        "ok_count": len(ok_records),
        "failed_count": len(failed_records),
        "backtest_count": len(backtested_records),
        "latest_created_at": records[-1].get("created_at") if records else None,
        "best_backtest": _compact_promotion_record(best_record) if best_record else None,
        "records": [_compact_promotion_record(record) for record in visible_records],
    }


def _best_backtest_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None

    def score(record: dict[str, Any]) -> float:
        backtest = record.get("backtest") or {}
        value = backtest.get("total_return")
        return float(value) if isinstance(value, int | float) else float("-inf")

    return max(records, key=score)


def _compact_promotion_record(record: dict[str, Any]) -> dict[str, Any]:
    backtest = record.get("backtest") or {}
    validation = record.get("validation") or {}
    smoke = validation.get("smoke") or {}
    return {
        "created_at": record.get("created_at"),
        "output": record.get("output"),
        "ok": bool(record.get("ok")),
        "backtest_requested": bool(record.get("backtest_requested")),
        "validation_rows": smoke.get("rows"),
        "total_return": backtest.get("total_return"),
        "sharpe": backtest.get("sharpe"),
        "trades": backtest.get("trades"),
    }
