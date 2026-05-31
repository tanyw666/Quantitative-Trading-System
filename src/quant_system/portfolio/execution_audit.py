from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def summarize_execution_audit(
    confirm_records: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    *,
    lookahead_days: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    buy_trades = [record for record in trade_records if str(record.get("side", "") or "").upper() == "BUY"]
    used_trade_indexes: set[int] = set()
    audits: list[dict[str, Any]] = []

    for confirm in confirm_records:
        trade_index = _match_trade_index(confirm, buy_trades, used_trade_indexes, lookahead_days=lookahead_days)
        trade = buy_trades[trade_index] if trade_index is not None else None
        if trade_index is not None:
            used_trade_indexes.add(trade_index)
        audits.append(_build_confirm_audit(confirm, trade))

    for index, trade in enumerate(buy_trades):
        if index in used_trade_indexes:
            continue
        audits.append(_build_orphan_trade_audit(trade))

    actionable = [item for item in audits if item["audit_type"] in {"confirm", "orphan_trade"}]
    aligned = [item for item in actionable if item["status"] == "pass"]
    warned = [item for item in actionable if item["status"] == "warn"]
    blocked = [item for item in actionable if item["status"] == "block"]
    missing_writeback = [item for item in audits if item["audit_type"] == "confirm" and item["trade_status"] == "missing_trade_log"]
    orphan_trades = [item for item in audits if item["audit_type"] == "orphan_trade"]
    linked_without_explicit = [item for item in audits if item.get("linked_by") == "fallback_symbol_date"]
    price_gaps = [float(item["trade_vs_confirm_price_gap_pct"]) for item in audits if item.get("trade_vs_confirm_price_gap_pct") is not None]
    quantity_gaps = [float(item["trade_vs_confirm_quantity_gap_pct"]) for item in audits if item.get("trade_vs_confirm_quantity_gap_pct") is not None]
    value_gaps = [float(item["trade_vs_confirm_value_gap_pct"]) for item in audits if item.get("trade_vs_confirm_value_gap_pct") is not None]
    confirm_status_counts = Counter(str(item.get("confirm_status", "") or "") for item in audits if item.get("confirm_status"))
    status_counts = Counter(str(item.get("status", "") or "") for item in audits if item.get("status"))
    visible_limit = max(int(limit), 0)

    return {
        "total_confirms": len(confirm_records),
        "total_buy_trades": len(buy_trades),
        "matched_trade_count": len(confirm_records) - len(missing_writeback),
        "missing_trade_writeback_count": len(missing_writeback),
        "missing_confirmation_trade_count": len(orphan_trades),
        "fallback_link_count": len(linked_without_explicit),
        "pass_count": len(aligned),
        "warn_count": len(warned),
        "block_count": len(blocked),
        "avg_trade_vs_confirm_price_gap_pct": _mean(price_gaps),
        "avg_trade_vs_confirm_quantity_gap_pct": _mean(quantity_gaps),
        "avg_trade_vs_confirm_value_gap_pct": _mean(value_gaps),
        "confirm_status_counts": dict(confirm_status_counts),
        "status_counts": dict(status_counts),
        "records": audits[-visible_limit:] if visible_limit else audits,
        "action_items": _action_items(
            missing_trade_writeback_count=len(missing_writeback),
            missing_confirmation_trade_count=len(orphan_trades),
            block_count=len(blocked),
            warn_count=len(warned),
            avg_price_gap=_mean(price_gaps),
        ),
    }


def render_execution_audit_lines(summary: dict[str, Any] | None) -> list[str]:
    if not summary or (
        int(summary.get("total_confirms", 0) or 0) == 0
        and int(summary.get("total_buy_trades", 0) or 0) == 0
    ):
        return ["- No execution confirmations or BUY trade records yet. Run `portfolio confirm`, then record fills with `review trade-add`."]

    lines = [
        f"- Confirm records: {int(summary.get('total_confirms', 0) or 0)}",
        f"- BUY trades: {int(summary.get('total_buy_trades', 0) or 0)}",
        f"- Matched trades: {int(summary.get('matched_trade_count', 0) or 0)}",
        f"- Missing trade writebacks: {int(summary.get('missing_trade_writeback_count', 0) or 0)}",
        f"- Trades missing confirmation: {int(summary.get('missing_confirmation_trade_count', 0) or 0)}",
        f"- Fallback links: {int(summary.get('fallback_link_count', 0) or 0)}",
        f"- pass/warn/block: {int(summary.get('pass_count', 0) or 0)} / {int(summary.get('warn_count', 0) or 0)} / {int(summary.get('block_count', 0) or 0)}",
        f"- Avg price gap: {float(summary.get('avg_trade_vs_confirm_price_gap_pct', 0) or 0):.2%}",
        f"- Avg quantity gap: {float(summary.get('avg_trade_vs_confirm_quantity_gap_pct', 0) or 0):.2%}",
        f"- Avg value gap: {float(summary.get('avg_trade_vs_confirm_value_gap_pct', 0) or 0):.2%}",
    ]
    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(["", "| Date | Symbol | Audit | Status | Confirm | Trade | PriceGap | QtyGap |", "| --- | --- | --- | --- | --- | --- | ---: | ---: |"])
        for item in records:
            lines.append(
                f"| {item.get('trade_date', item.get('confirm_date', ''))} | {item.get('symbol', '')} | "
                f"{item.get('audit_type', '')} | {item.get('status', '')} | {item.get('confirm_status', '')} | "
                f"{item.get('trade_status', '')} | {_pct(item.get('trade_vs_confirm_price_gap_pct'))} | {_pct(item.get('trade_vs_confirm_quantity_gap_pct'))} |"
            )
            reasons = list(item.get("reasons", []) or [])
            for reason in reasons[:2]:
                lines.append(f"  - {reason}")
    action_items = list(summary.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def render_execution_audit_markdown(summary: dict[str, Any] | None) -> str:
    return "\n".join(["# Execution Audit", "", *render_execution_audit_lines(summary), ""])


def _build_confirm_audit(confirm: dict[str, Any], trade: dict[str, Any] | None) -> dict[str, Any]:
    confirm_status = str(confirm.get("status", "") or "")
    symbol = str(confirm.get("symbol", "") or "").zfill(6)
    record = {
        "audit_type": "confirm",
        "confirm_created_at": str(confirm.get("created_at", "") or ""),
        "confirm_date": _record_date(confirm),
        "trade_date": _record_date(trade) if trade else "",
        "symbol": symbol,
        "confirm_status": confirm_status,
        "trade_status": "matched" if trade else "missing_trade_log",
        "linked_by": "confirmation_id" if trade and str(trade.get("execution_confirmation_created_at", "") or "") == str(confirm.get("created_at", "") or "") else ("fallback_symbol_date" if trade else ""),
        "trade_vs_confirm_price_gap_pct": None,
        "trade_vs_confirm_quantity_gap_pct": None,
        "trade_vs_confirm_value_gap_pct": None,
        "reasons": [],
    }
    if trade is None:
        record["status"] = "block" if confirm_status in {"pass", "warn"} else "warn"
        record["reasons"] = ["Execution confirmation exists, but no matching trade writeback was found."]
        return record

    reasons: list[str] = []
    status = "pass"
    trade_price = _float_or_none(trade.get("price"))
    confirm_price = _float_or_none(confirm.get("current_price"))
    if trade_price not in (None, 0) and confirm_price not in (None, 0):
        record["trade_vs_confirm_price_gap_pct"] = trade_price / confirm_price - 1.0
        if record["trade_vs_confirm_price_gap_pct"] > 0.02:
            status = "block"
            reasons.append(f"Actual fill price was {record['trade_vs_confirm_price_gap_pct']:.1%} above confirmation price.")
        elif record["trade_vs_confirm_price_gap_pct"] > 0.01:
            status = _escalate(status, "warn")
            reasons.append(f"Actual fill price was {record['trade_vs_confirm_price_gap_pct']:.1%} above confirmation price.")
    trade_qty = int(trade.get("quantity", 0) or 0)
    confirm_qty = int(confirm.get("suggested_quantity", 0) or 0)
    if confirm_qty > 0:
        record["trade_vs_confirm_quantity_gap_pct"] = trade_qty / confirm_qty - 1.0
        if trade_qty > confirm_qty:
            status = "block"
            reasons.append(f"Actual quantity {trade_qty} exceeded confirmed quantity {confirm_qty}.")
        elif trade_qty < confirm_qty:
            status = _escalate(status, "warn")
            reasons.append(f"Actual quantity {trade_qty} was below confirmed quantity {confirm_qty}; verify partial fill or manual reduction.")
    trade_amount = _float_or_none(trade.get("amount"))
    confirm_value = _float_or_none(confirm.get("confirmed_value"))
    if trade_amount is not None and confirm_value not in (None, 0):
        record["trade_vs_confirm_value_gap_pct"] = trade_amount / confirm_value - 1.0
    if confirm_status == "block":
        status = "block"
        reasons.append("Confirmation status was block, but a BUY trade was still recorded.")
    elif confirm_status == "warn":
        status = _escalate(status, "warn")
        reasons.append("Confirmation status was warn; execution requires a review of why it continued.")
    if not str(trade.get("execution_confirmation_created_at", "") or ""):
        status = _escalate(status, "warn")
        reasons.append("Trade record was not explicitly bound to an execution confirmation and only matched by symbol/date fallback.")
    if not str(trade.get("review", "") or "").strip():
        status = _escalate(status, "warn")
        reasons.append("Trade record has no post-fill review note.")
    record["status"] = status
    record["reasons"] = reasons or ["Trade is aligned with the execution confirmation."]
    return record


def _build_orphan_trade_audit(trade: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_type": "orphan_trade",
        "confirm_created_at": "",
        "confirm_date": "",
        "trade_date": _record_date(trade),
        "symbol": str(trade.get("symbol", "") or "").zfill(6),
        "confirm_status": "",
        "trade_status": "missing_confirmation",
        "linked_by": "",
        "trade_vs_confirm_price_gap_pct": None,
        "trade_vs_confirm_quantity_gap_pct": None,
        "trade_vs_confirm_value_gap_pct": None,
        "status": "block" if _trade_looks_planned(trade) else "warn",
        "reasons": ["BUY trade has no matching execution confirmation."],
    }


def _match_trade_index(
    confirm: dict[str, Any],
    buy_trades: list[dict[str, Any]],
    used_trade_indexes: set[int],
    *,
    lookahead_days: int,
) -> int | None:
    confirm_id = str(confirm.get("created_at", "") or "")
    if confirm_id:
        for index, trade in enumerate(buy_trades):
            if index in used_trade_indexes:
                continue
            if str(trade.get("execution_confirmation_created_at", "") or "") == confirm_id:
                return index
    symbol = str(confirm.get("symbol", "") or "").zfill(6)
    confirm_date = _record_date(confirm)
    start = _parse_date(confirm_date)
    for index, trade in enumerate(buy_trades):
        if index in used_trade_indexes:
            continue
        if str(trade.get("symbol", "") or "").zfill(6) != symbol:
            continue
        trade_date = _parse_date(_record_date(trade))
        if start is None or trade_date is None:
            continue
        delta_days = (trade_date - start).days
        if 0 <= delta_days <= lookahead_days:
            return index
    return None


def _trade_looks_planned(trade: dict[str, Any]) -> bool:
    return bool(
        trade.get("planned_price")
        or trade.get("planned_pct")
        or trade.get("gate_status")
        or trade.get("execution_confirmation_status")
    )


def _record_date(record: dict[str, Any] | None) -> str:
    if not record:
        return ""
    return str(record.get("trade_date") or record.get("date") or record.get("created_at") or "")[:10]


def _parse_date(value: str) -> datetime.date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _escalate(current: str, target: str) -> str:
    rank = {"pass": 0, "warn": 1, "block": 2}
    return target if rank.get(target, 0) > rank.get(current, 0) else current


def _action_items(
    *,
    missing_trade_writeback_count: int,
    missing_confirmation_trade_count: int,
    block_count: int,
    warn_count: int,
    avg_price_gap: float,
) -> list[str]:
    items: list[str] = []
    if missing_trade_writeback_count:
        items.append("Execution confirmations exist without trade writebacks; confirm whether orders were cancelled, skipped, or missing from the journal.")
    if missing_confirmation_trade_count:
        items.append("BUY trades without execution confirmations exist; require `portfolio confirm` before every new manual order.")
    if block_count:
        items.append("Block-level execution deviations exist; next trading day should pause new BUY orders until reviewed.")
    if warn_count and not block_count:
        items.append("Warn-level execution deviations exist; tighten price chasing and manual size changes.")
    if abs(avg_price_gap) > 0.01:
        items.append("Average fill price deviates from confirmation price by more than 1%; check chasing, liquidity, or stale confirmation inputs.")
    if not items:
        items.append("Execution confirmation and trade writeback chain is clean in the current sample.")
    return items


def _pct(value: object) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.2%}"
