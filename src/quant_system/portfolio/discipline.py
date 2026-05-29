from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from quant_system.reports.discipline_advice import render_discipline_advice_lines
from quant_system.storage.jsonl import append_jsonl, read_jsonl
from quant_system.storage.sqlite_store import SQLiteStore


def build_discipline_record(
    *,
    source: str,
    gate_review: dict | None = None,
    trade_stats: dict | None = None,
    holding_risk: dict | None = None,
    allocation_plan: dict | None = None,
    record_date: str | None = None,
) -> dict[str, Any]:
    gate_review = gate_review or {}
    trade_stats = trade_stats or {}
    holding_risk = holding_risk or {}
    allocation_plan = allocation_plan or {}
    advice = render_discipline_advice_lines(
        gate_review=gate_review,
        trade_stats=trade_stats,
        holding_risk=holding_risk,
        allocation_plan=allocation_plan,
    )
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "date": record_date or date.today().isoformat(),
        "source": source,
        "status": _discipline_status(gate_review, trade_stats, holding_risk, allocation_plan),
        "advice": advice,
        "gate_violation_count": int(gate_review.get("violation_count", 0) or 0),
        "missing_gate_count": int(gate_review.get("missing_gate_count", 0) or 0),
        "avg_execution_deviation_pct": float(trade_stats.get("avg_execution_deviation_pct", 0) or 0),
        "mistake_counts": dict(trade_stats.get("mistake_counts", {}) or {}),
        "holding_status": str(holding_risk.get("status", "") or ""),
        "target_exposure_pct": float(allocation_plan.get("target_exposure_pct", 0) or 0),
        "allocated_pct": float(allocation_plan.get("allocated_pct", 0) or 0),
    }


def persist_discipline_record(record: dict[str, Any], log_path: Path | None = None, sqlite_path: Path | None = None) -> None:
    if log_path is not None:
        append_jsonl(log_path, record)
    if sqlite_path is not None:
        SQLiteStore(sqlite_path).insert_discipline_record(record)


def read_discipline_records(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def summarize_discipline_records(records: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status", "") or "") for record in records if record.get("status"))
    source_counts = Counter(str(record.get("source", "") or "") for record in records if record.get("source"))
    advice_counts: Counter[str] = Counter()
    for record in records:
        advice_counts.update(str(item) for item in record.get("advice", []) or [] if str(item))
    visible = records[-limit:] if limit > 0 else records
    return {
        "total": len(records),
        "pass_count": status_counts.get("pass", 0),
        "warn_count": status_counts.get("warn", 0),
        "block_count": status_counts.get("block", 0),
        "by_status": dict(status_counts),
        "by_source": dict(source_counts),
        "top_advice": dict(advice_counts.most_common(5)),
        "latest_created_at": records[-1].get("created_at") if records else None,
        "records": visible,
    }


def _discipline_status(gate_review: dict, trade_stats: dict, holding_risk: dict, allocation_plan: dict) -> str:
    holding_status = str(holding_risk.get("status", "") or "")
    target = float(allocation_plan.get("target_exposure_pct", 0) or 0)
    allocated = float(allocation_plan.get("allocated_pct", 0) or 0)
    if holding_status == "block" or (target == 0 and allocated > 0):
        return "block"
    if (
        int(gate_review.get("violation_count", 0) or 0)
        or int(gate_review.get("missing_gate_count", 0) or 0)
        or abs(float(trade_stats.get("avg_execution_deviation_pct", 0) or 0)) >= 0.02
        or trade_stats.get("mistake_counts")
        or holding_status == "warn"
        or (target > 0 and allocated > target * 1.05)
    ):
        return "warn"
    return "pass"
