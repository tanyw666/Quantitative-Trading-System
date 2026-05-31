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
from quant_system.storage.sqlite_store import SQLiteStore
from quant_system.strategies.registry import create_strategy_from_config


@dataclass(frozen=True)
class StrategyPromotionResult:
    created_at: str
    summary: str
    output: str
    strategy_name: str
    ok: bool
    backtest_requested: bool
    buy_price_field: str
    execution_timing: str
    cash: float
    validation: dict[str, Any]
    backtest: dict[str, Any] = field(default_factory=dict)
    trade_plan_audit: dict[str, Any] = field(default_factory=dict)
    trade_plan_pressure: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "summary": self.summary,
            "output": self.output,
            "strategy_name": self.strategy_name,
            "ok": self.ok,
            "backtest_requested": self.backtest_requested,
            "buy_price_field": self.buy_price_field,
            "execution_timing": self.execution_timing,
            "cash": self.cash,
            "validation": self.validation,
            "backtest": self.backtest,
            "trade_plan_audit": self.trade_plan_audit,
            "trade_plan_pressure": self.trade_plan_pressure,
        }


def promote_strategy_from_summary(
    summary_path: Path,
    output_path: Path,
    name: str | None = None,
    description: str | None = None,
    frame: pd.DataFrame | None = None,
    backtest: bool = False,
    buy_price_field: str = "open",
    execution_timing: str = "next_bar",
    cash: float = 100000.0,
    trade_plan_pressure: dict[str, Any] | None = None,
) -> StrategyPromotionResult:
    summary = load_experiment_summary(summary_path)
    config = strategy_config_from_summary(summary, name=name, description=description)
    write_strategy_config(output_path, config)

    validation = validate_strategy_config(output_path, frame=frame, trade_plan_pressure=trade_plan_pressure)
    backtest_summary: dict[str, Any] = {}
    if validation.ok and backtest and frame is not None:
        strategy = create_strategy_from_config(output_path)
        backtest_summary = BacktestEngine(
            BacktestConfig(initial_cash=cash, buy_price_field=buy_price_field, execution_timing=execution_timing)
        ).run(frame, strategy).summary()

    pressure = _trade_plan_pressure_from_validation(validation.to_dict(), trade_plan_pressure)

    return StrategyPromotionResult(
        created_at=datetime.now(timezone.utc).isoformat(),
        summary=str(summary_path),
        output=str(output_path),
        strategy_name=str(config.get("name", "")),
        ok=validation.ok,
        backtest_requested=backtest,
        buy_price_field=buy_price_field,
        execution_timing=execution_timing,
        cash=cash,
        validation=validation.to_dict(),
        backtest=backtest_summary,
        trade_plan_pressure=pressure,
    )


def append_promotion_record(path: Path, result: StrategyPromotionResult) -> None:
    append_jsonl(path, result.to_dict())


def read_promotion_records(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def persist_promotion_record(path: Path, result: StrategyPromotionResult, sqlite_path: Path | None = None) -> None:
    payload = result.to_dict()
    append_jsonl(path, payload)
    if sqlite_path is not None:
        store = SQLiteStore(sqlite_path)
        store.init()
        store.insert_strategy_promotion(payload)


def summarize_promotion_records(records: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    visible_records = records[-limit:] if limit > 0 else records
    ok_records = [record for record in records if record.get("ok")]
    failed_records = [record for record in records if not record.get("ok")]
    backtested_records = [record for record in records if record.get("backtest")]
    trade_plan_pressure = _latest_trade_plan_pressure(records)

    best_record = _best_backtest_record(backtested_records)
    return {
        "total": len(records),
        "ok_count": len(ok_records),
        "failed_count": len(failed_records),
        "backtest_count": len(backtested_records),
        "latest_created_at": records[-1].get("created_at") if records else None,
        "best_backtest": _compact_promotion_record(best_record) if best_record else None,
        "trade_plan_pressure": trade_plan_pressure,
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
    trade_plan_pressure = record.get("trade_plan_pressure") or {}
    return {
        "created_at": record.get("created_at"),
        "output": record.get("output"),
        "ok": bool(record.get("ok")),
        "backtest_requested": bool(record.get("backtest_requested")),
        "validation_rows": smoke.get("rows"),
        "total_return": backtest.get("total_return"),
        "sharpe": backtest.get("sharpe"),
        "trades": backtest.get("trades"),
        "trade_plan_status": trade_plan_pressure.get("status"),
        "trade_plan_action": trade_plan_pressure.get("action"),
        "trade_plan_score": trade_plan_pressure.get("score"),
    }


def _latest_trade_plan_pressure(records: list[dict[str, Any]]) -> dict[str, Any]:
    for record in reversed(records):
        pressure = record.get("trade_plan_pressure") or {}
        if pressure:
            return _compact_trade_plan_pressure(pressure)
    return {}


def _compact_trade_plan_pressure(pressure: dict[str, Any]) -> dict[str, Any]:
    return {
        "score": round(float(pressure.get("score", 0) or 0), 2),
        "status": str(pressure.get("status", "") or ""),
        "action": str(pressure.get("action", "") or ""),
        "match_rate": float(pressure.get("match_rate", 0) or 0) if pressure.get("match_rate") not in (None, "") else None,
        "unmatched_plans": int(pressure.get("unmatched_plans", 0) or 0),
        "orphan_trades": int(pressure.get("orphan_trades", 0) or 0),
        "avg_price_deviation_pct": float(pressure.get("avg_price_deviation_pct", 0) or 0)
        if pressure.get("avg_price_deviation_pct") not in (None, "")
        else None,
        "alerts": list(pressure.get("alerts", []) or []),
    }


def _trade_plan_pressure_from_validation(
    validation: dict[str, Any],
    trade_plan_pressure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    score = float(validation.get("score", 0) or 0)
    status = str(validation.get("status", "") or "")
    action = str(validation.get("action", "") or "")
    alerts = list(validation.get("alerts", []) or [])
    pressure = trade_plan_pressure or {}
    match_rate = float(pressure.get("match_rate", 0) or 0)
    unmatched_plans = int(pressure.get("unmatched_plans", 0) or 0)
    orphan_trades = int(pressure.get("orphan_trades", 0) or 0)
    avg_price_deviation_pct = abs(float(pressure.get("avg_price_deviation_pct", 0) or 0))
    if match_rate > 0:
        score = max(score - min((1.0 - match_rate) * 20.0, 15.0), 0.0)
    if unmatched_plans:
        score = max(score - min(unmatched_plans * 3.0, 9.0), 0.0)
    if orphan_trades:
        score = max(score - min(orphan_trades * 4.0, 12.0), 0.0)
    if avg_price_deviation_pct > 0.03:
        score = max(score - min(avg_price_deviation_pct * 100.0, 10.0), 0.0)
    return {
        "score": round(score, 2),
        "status": status,
        "action": action,
        "alerts": alerts,
        "match_rate": match_rate if match_rate > 0 else None,
        "unmatched_plans": unmatched_plans,
        "orphan_trades": orphan_trades,
        "avg_price_deviation_pct": avg_price_deviation_pct if avg_price_deviation_pct > 0 else None,
    }
