from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any


DISCIPLINE_SAME_DAY_SOURCES = ("premarket", "briefing", "workflow")


def evaluate_discipline_adherence(
    discipline_records: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    lookahead_days: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    lookahead_days = max(int(lookahead_days or 1), 1)
    trade_index = _normalise_trades(trade_records)
    results: list[dict[str, Any]] = []
    for record in discipline_records:
        record_date = _parse_date(record.get("date") or record.get("record_date"))
        if record_date is None:
            continue
        start_date = _adherence_start_date(record, record_date)
        end_date = start_date + timedelta(days=lookahead_days - 1)
        window_trades = [
            trade
            for trade in trade_index
            if start_date <= trade["trade_date_obj"] <= end_date
        ]
        results.append(_evaluate_record(record, start_date, end_date, window_trades))
    return summarize_discipline_adherence(results, limit=limit)


def summarize_discipline_adherence(results: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    status_counts = Counter(str(item.get("adherence_status", "") or "") for item in results)
    violation_counts: Counter[str] = Counter()
    for item in results:
        violation_counts.update(str(value) for value in item.get("violations", []) or [] if str(value))
    visible_limit = max(int(limit or 0), 0)
    visible = results[-visible_limit:] if visible_limit else results
    total = len(results)
    pass_count = status_counts.get("pass", 0)
    violation_count = total - pass_count
    exception_count = sum(int(item.get("approved_exception_count", 0) or 0) for item in results)
    return {
        "total": total,
        "pass_count": pass_count,
        "warn_count": status_counts.get("warn", 0),
        "block_count": status_counts.get("block", 0),
        "violation_count": violation_count,
        "exception_count": exception_count,
        "adherence_rate": pass_count / total if total else 0.0,
        "by_status": dict(status_counts),
        "by_violation": dict(violation_counts.most_common()),
        "records": visible,
    }


def _evaluate_record(
    record: dict[str, Any],
    start_date: date,
    end_date: date,
    window_trades: list[dict[str, Any]],
) -> dict[str, Any]:
    status = str(record.get("status", "") or "pass").strip().lower()
    buys = [trade for trade in window_trades if trade["side"] == "BUY"]
    exception_buys = [trade for trade in buys if trade["discipline_exception"]]
    explained_exception_buys = [trade for trade in exception_buys if trade["exception_reason"]]
    unexplained_exception_buys = [trade for trade in exception_buys if not trade["exception_reason"]]
    rule_buys = [trade for trade in buys if not _is_explained_exception(trade)]
    violations: list[str] = []
    notes: list[str] = []

    if status == "block" and rule_buys:
        violations.append("new_buy_after_block")
    if status == "warn":
        warned_buys = [trade for trade in rule_buys if trade["gate_status"] in {"warn", "block"}]
        if warned_buys:
            violations.append("warn_block_buy_after_warn")
    if _requires_gate_snapshot(record):
        missing_gate_buys = [
            trade
            for trade in buys
            if not trade["gate_status"] and not trade["workflow_summary"]
        ]
        if missing_gate_buys:
            violations.append("missing_gate_snapshot_after_advice")
    if _zero_exposure_block(record) and rule_buys:
        violations.append("new_buy_under_zero_exposure")
    if unexplained_exception_buys:
        violations.append("unexplained_discipline_exception")

    if not buys:
        notes.append("No BUY in the adherence window.")
    if explained_exception_buys:
        notes.append("Documented discipline exception was excluded from rule-breach counts.")
    elif not violations:
        notes.append("BUY activity did not breach the recorded discipline status.")

    return {
        "date": str(record.get("date") or record.get("record_date") or ""),
        "source": str(record.get("source", "") or ""),
        "status": status,
        "applicable_start": start_date.isoformat(),
        "applicable_end": end_date.isoformat(),
        "adherence_status": _adherence_status(status, violations),
        "violations": violations,
        "trade_count_next_window": len(window_trades),
        "buy_count_next_window": len(buys),
        "exception_count_next_window": len(exception_buys),
        "approved_exception_count": len(explained_exception_buys),
        "matched_trades": [_public_trade_fields(trade) for trade in window_trades],
        "notes": notes,
    }


def _normalise_trades(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for record in records:
        trade_date = _parse_date(record.get("date") or record.get("trade_date"))
        if trade_date is None:
            continue
        trades.append(
            {
                "trade_date_obj": trade_date,
                "date": trade_date.isoformat(),
                "symbol": str(record.get("symbol", "") or "").zfill(6),
                "name": str(record.get("name", "") or ""),
                "side": str(record.get("side", "") or "").strip().upper(),
                "strategy": str(record.get("strategy", "") or ""),
                "amount": float(record.get("amount", 0) or 0),
                "gate_status": str(record.get("gate_status", "") or "").strip().lower(),
                "gate_message": str(record.get("gate_message", "") or ""),
                "workflow_summary": str(record.get("workflow_summary", "") or ""),
                "discipline_exception": _truthy(record.get("discipline_exception")),
                "exception_reason": str(record.get("exception_reason", "") or "").strip(),
            }
        )
    return sorted(trades, key=lambda item: (item["trade_date_obj"], item["symbol"], item["side"]))


def _parse_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _adherence_start_date(record: dict[str, Any], record_date: date) -> date:
    source = str(record.get("source", "") or "").lower()
    if any(item in source for item in DISCIPLINE_SAME_DAY_SOURCES):
        return record_date
    return record_date + timedelta(days=1)


def _requires_gate_snapshot(record: dict[str, Any]) -> bool:
    if int(record.get("missing_gate_count", 0) or 0) > 0:
        return True
    advice = " ".join(str(item).lower() for item in record.get("advice", []) or [])
    return "gate snapshot" in advice or "workflow summary" in advice


def _zero_exposure_block(record: dict[str, Any]) -> bool:
    target = float(record.get("target_exposure_pct", 0) or 0)
    allocated = float(record.get("allocated_pct", 0) or 0)
    return target == 0 and allocated > 0


def _is_explained_exception(trade: dict[str, Any]) -> bool:
    return bool(trade.get("discipline_exception")) and bool(str(trade.get("exception_reason", "") or "").strip())


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _adherence_status(status: str, violations: list[str]) -> str:
    if not violations:
        return "pass"
    if status == "block" or "new_buy_under_zero_exposure" in violations:
        return "block"
    return "warn"


def _public_trade_fields(trade: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": trade["date"],
        "symbol": trade["symbol"],
        "name": trade["name"],
        "side": trade["side"],
        "strategy": trade["strategy"],
        "amount": trade["amount"],
        "gate_status": trade["gate_status"],
        "gate_message": trade["gate_message"],
        "workflow_summary": trade["workflow_summary"],
        "discipline_exception": trade["discipline_exception"],
        "exception_reason": trade["exception_reason"],
    }
