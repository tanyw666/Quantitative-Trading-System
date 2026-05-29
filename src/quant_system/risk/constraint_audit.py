from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from quant_system.storage.jsonl import append_jsonl, read_jsonl
from quant_system.storage.sqlite_store import SQLiteStore


def build_constraint_audit_record(source: str, constraint: dict | None, symbol: str = "") -> dict[str, Any] | None:
    if not constraint:
        return None
    alert_level = str(constraint.get("alert_level", "pass") or "pass")
    if alert_level == "pass":
        return None
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "strategy": str(constraint.get("strategy", "") or ""),
        "symbol": str(symbol or constraint.get("symbol", "") or ""),
        "alert_level": alert_level,
        "action": str(constraint.get("action", "") or ""),
        "alerts": list(constraint.get("alerts", []) or []),
        "note": str(constraint.get("note", "") or ""),
    }


def persist_constraint_audit(
    record: dict[str, Any] | None,
    log_path: Path | None = None,
    sqlite_path: Path | None = None,
) -> None:
    if not record:
        return
    if log_path is not None:
        append_jsonl(log_path, record)
    if sqlite_path is not None:
        SQLiteStore(sqlite_path).insert_strategy_constraint(record)


def read_constraint_audit_records(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def summarize_constraint_audit_records(records: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    strategy_counts = Counter(str(record.get("strategy", "")) for record in records if record.get("strategy"))
    source_counts = Counter(str(record.get("source", "")) for record in records if record.get("source"))
    alert_level_counts = Counter(str(record.get("alert_level", "")) for record in records if record.get("alert_level"))
    alert_counts: Counter[str] = Counter()
    for record in records:
        alerts = record.get("alerts", []) or []
        alert_counts.update(str(item) for item in alerts if str(item))

    visible = records[-limit:] if limit > 0 else records
    return {
        "total": len(records),
        "warn_count": alert_level_counts.get("warn", 0),
        "block_count": alert_level_counts.get("block", 0),
        "by_strategy": dict(strategy_counts),
        "by_source": dict(source_counts),
        "by_alert_level": dict(alert_level_counts),
        "by_alert": dict(alert_counts),
        "trend": summarize_constraint_trend(records),
        "latest_created_at": records[-1].get("created_at") if records else None,
        "records": visible,
    }


def summarize_constraint_trend(records: list[dict[str, Any]], windows: tuple[int, ...] = (5, 10)) -> dict[str, Any]:
    dated = [(record, _record_date(record)) for record in records if _record_date(record)]
    if not dated:
        return {}
    end = max(item_date for _record, item_date in dated if item_date is not None)
    trend: dict[str, Any] = {"as_of": end.isoformat(), "windows": {}}
    for window in windows:
        start = end - timedelta(days=max(window - 1, 0))
        recent = [record for record, item_date in dated if item_date is not None and start <= item_date <= end]
        level_counts = Counter(str(record.get("alert_level", "")) for record in recent if record.get("alert_level"))
        strategy_counts = Counter(str(record.get("strategy", "")) for record in recent if record.get("strategy"))
        trend["windows"][str(window)] = {
            "total": len(recent),
            "warn_count": level_counts.get("warn", 0),
            "block_count": level_counts.get("block", 0),
            "top_strategy": strategy_counts.most_common(1)[0][0] if strategy_counts else "",
        }
    return trend


def _record_date(record: dict[str, Any]) -> date | None:
    value = str(record.get("created_at") or record.get("date") or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            return None
