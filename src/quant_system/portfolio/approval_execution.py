from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def summarize_approval_execution(
    approval_records: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    *,
    lookahead_days: int = 1,
    value_tolerance_pct: float = 0.02,
    limit: int = 20,
) -> dict[str, Any]:
    buy_trades = [record for record in trade_records if str(record.get("side", "") or "").upper() == "BUY"]
    used_trade_indexes: set[int] = set()
    audits: list[dict[str, Any]] = []

    for approval in approval_records:
        trade_index = _match_trade_index(approval, buy_trades, used_trade_indexes, lookahead_days=lookahead_days)
        trade = buy_trades[trade_index] if trade_index is not None else None
        if trade_index is not None:
            used_trade_indexes.add(trade_index)
        audits.append(_build_approval_audit(approval, trade, value_tolerance_pct=value_tolerance_pct))

    for index, trade in enumerate(buy_trades):
        if index in used_trade_indexes:
            continue
        audits.append(_build_orphan_trade_audit(trade))

    actionable = [item for item in audits if item["audit_type"] in {"approval", "orphan_trade"}]
    status_counts = Counter(str(item.get("status", "") or "") for item in actionable)
    approval_status_counts = Counter(str(item.get("approval_status", "") or "") for item in audits if item.get("approval_status"))
    missing_execution = [item for item in audits if item["audit_type"] == "approval" and item["trade_status"] == "missing_trade_log"]
    orphan_trades = [item for item in audits if item["audit_type"] == "orphan_trade"]
    block_violations = [
        item
        for item in audits
        if item["audit_type"] == "approval"
        and item.get("approval_status") == "block"
        and item.get("trade_status") == "matched"
    ]
    fallback_links = [item for item in audits if item.get("linked_by") == "fallback_symbol_date"]
    quantity_gaps = [float(item["trade_vs_approval_quantity_gap_pct"]) for item in audits if item.get("trade_vs_approval_quantity_gap_pct") is not None]
    value_gaps = [float(item["trade_vs_approval_value_gap_pct"]) for item in audits if item.get("trade_vs_approval_value_gap_pct") is not None]
    visible_limit = max(int(limit), 0)

    return {
        "total_approvals": len(approval_records),
        "total_buy_trades": len(buy_trades),
        "matched_trade_count": len(approval_records) - len(missing_execution),
        "approved_not_executed_count": len(missing_execution),
        "missing_approval_trade_count": len(orphan_trades),
        "block_approval_executed_count": len(block_violations),
        "fallback_link_count": len(fallback_links),
        "pass_count": int(status_counts.get("pass", 0)),
        "warn_count": int(status_counts.get("warn", 0)),
        "block_count": int(status_counts.get("block", 0)),
        "avg_trade_vs_approval_quantity_gap_pct": _mean(quantity_gaps),
        "avg_trade_vs_approval_value_gap_pct": _mean(value_gaps),
        "approval_status_counts": dict(approval_status_counts),
        "status_counts": dict(status_counts),
        "records": audits[-visible_limit:] if visible_limit else audits,
        "action_items": _action_items(
            approved_not_executed_count=len(missing_execution),
            missing_approval_trade_count=len(orphan_trades),
            block_approval_executed_count=len(block_violations),
            fallback_link_count=len(fallback_links),
            block_count=int(status_counts.get("block", 0)),
            warn_count=int(status_counts.get("warn", 0)),
        ),
    }


def render_approval_execution_lines(summary: dict[str, Any] | None) -> list[str]:
    if not summary or (
        int(summary.get("total_approvals", 0) or 0) == 0
        and int(summary.get("total_buy_trades", 0) or 0) == 0
    ):
        return ["- No approval or BUY trade records yet. Run `portfolio approve --record`, then record the fill with `review trade-add --order-approval`."]

    lines = [
        f"- Approvals: {int(summary.get('total_approvals', 0) or 0)}",
        f"- BUY trades: {int(summary.get('total_buy_trades', 0) or 0)}",
        f"- Matched trades: {int(summary.get('matched_trade_count', 0) or 0)}",
        f"- Approved but not executed: {int(summary.get('approved_not_executed_count', 0) or 0)}",
        f"- Trades missing approval: {int(summary.get('missing_approval_trade_count', 0) or 0)}",
        f"- Block approvals executed: {int(summary.get('block_approval_executed_count', 0) or 0)}",
        f"- Fallback links: {int(summary.get('fallback_link_count', 0) or 0)}",
        f"- pass/warn/block: {int(summary.get('pass_count', 0) or 0)} / {int(summary.get('warn_count', 0) or 0)} / {int(summary.get('block_count', 0) or 0)}",
        f"- Avg quantity gap: {float(summary.get('avg_trade_vs_approval_quantity_gap_pct', 0) or 0):.2%}",
        f"- Avg value gap: {float(summary.get('avg_trade_vs_approval_value_gap_pct', 0) or 0):.2%}",
    ]
    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(["", "| Date | Symbol | Audit | Status | Approval | Trade | QtyGap | ValueGap |", "| --- | --- | --- | --- | --- | --- | ---: | ---: |"])
        for item in records:
            lines.append(
                f"| {item.get('trade_date', item.get('approval_date', ''))} | {item.get('symbol', '')} | "
                f"{item.get('audit_type', '')} | {item.get('status', '')} | {item.get('approval_status', '')} | "
                f"{item.get('trade_status', '')} | {_pct(item.get('trade_vs_approval_quantity_gap_pct'))} | {_pct(item.get('trade_vs_approval_value_gap_pct'))} |"
            )
            for reason in list(item.get("reasons", []) or [])[:2]:
                lines.append(f"  - {reason}")
    action_items = list(summary.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def render_approval_execution_markdown(summary: dict[str, Any] | None) -> str:
    return "\n".join(["# Approval Execution Audit", "", *render_approval_execution_lines(summary), ""])


def _build_approval_audit(
    approval: dict[str, Any],
    trade: dict[str, Any] | None,
    *,
    value_tolerance_pct: float,
) -> dict[str, Any]:
    approval_status = str(approval.get("status", "") or "")
    symbol = str(approval.get("symbol", "") or "").zfill(6)
    record = {
        "audit_type": "approval",
        "approval_created_at": str(approval.get("created_at", "") or ""),
        "approval_date": _record_date(approval),
        "trade_date": _record_date(trade) if trade else "",
        "symbol": symbol,
        "strategy": _strategy_from(approval, trade),
        "approval_status": approval_status,
        "trade_status": "matched" if trade else "missing_trade_log",
        "linked_by": _linked_by(approval, trade),
        "trade_vs_approval_quantity_gap_pct": None,
        "trade_vs_approval_value_gap_pct": None,
        "reasons": [],
    }
    if trade is None:
        record["status"] = "pass" if approval_status == "block" else "warn"
        record["reasons"] = (
            ["Blocked approval was not executed."]
            if approval_status == "block"
            else ["Approval exists but no matching BUY trade was recorded within the lookahead window."]
        )
        return record

    status = "pass"
    reasons: list[str] = []
    trade_qty = int(trade.get("quantity", 0) or 0)
    approved_qty = int(approval.get("suggested_quantity", 0) or 0)
    if approved_qty > 0:
        record["trade_vs_approval_quantity_gap_pct"] = trade_qty / approved_qty - 1.0
        if trade_qty > approved_qty:
            status = "block"
            reasons.append(f"Trade quantity {trade_qty} exceeded approved quantity {approved_qty}.")
        elif trade_qty < approved_qty:
            status = _escalate(status, "warn")
            reasons.append(f"Trade quantity {trade_qty} was below approved quantity {approved_qty}; verify whether this was partial fill or manual reduction.")
    elif trade_qty > 0:
        status = "block"
        reasons.append("Approval suggested zero shares, but a BUY trade was recorded.")

    trade_value = _trade_value(trade)
    approved_value = _float_or_none(approval.get("confirmed_value"))
    if approved_value not in (None, 0):
        record["trade_vs_approval_value_gap_pct"] = trade_value / approved_value - 1.0
        if trade_value > approved_value * (1 + max(float(value_tolerance_pct), 0.0)):
            status = "block"
            reasons.append(f"Trade value {trade_value:.2f} exceeded approved value {approved_value:.2f}.")
    elif trade_value > 0:
        status = "block"
        reasons.append("Approval confirmed zero value, but a BUY trade was recorded.")

    if approval_status == "block":
        status = "block"
        reasons.append("Approval status was block, but a BUY trade was still recorded.")
    elif approval_status == "warn":
        status = _escalate(status, "warn")
        reasons.append("Approval status was warn; execution requires explicit manual acceptance.")
    if record["linked_by"] == "fallback_symbol_date":
        status = _escalate(status, "warn")
        reasons.append("Trade was matched by symbol/date fallback instead of explicit approval id.")
    if not str(trade.get("review", "") or "").strip():
        status = _escalate(status, "warn")
        reasons.append("Trade record has no review note.")

    record["status"] = status
    record["reasons"] = reasons or ["Trade stayed within the final approval."]
    return record


def _build_orphan_trade_audit(trade: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_type": "orphan_trade",
        "approval_created_at": "",
        "approval_date": "",
        "trade_date": _record_date(trade),
        "symbol": str(trade.get("symbol", "") or "").zfill(6),
        "strategy": str(trade.get("strategy", "") or ""),
        "approval_status": "",
        "trade_status": "missing_approval",
        "linked_by": "",
        "trade_vs_approval_quantity_gap_pct": None,
        "trade_vs_approval_value_gap_pct": None,
        "status": "block" if _trade_looks_planned(trade) else "warn",
        "reasons": ["BUY trade has no matching final order approval."],
    }


def _match_trade_index(
    approval: dict[str, Any],
    buy_trades: list[dict[str, Any]],
    used_trade_indexes: set[int],
    *,
    lookahead_days: int,
) -> int | None:
    approval_id = str(approval.get("created_at", "") or "")
    if approval_id:
        for index, trade in enumerate(buy_trades):
            if index in used_trade_indexes:
                continue
            if str(trade.get("order_approval_created_at", "") or "") == approval_id:
                return index
    symbol = str(approval.get("symbol", "") or "").zfill(6)
    start = _parse_date(_record_date(approval))
    for index, trade in enumerate(buy_trades):
        if index in used_trade_indexes:
            continue
        if str(trade.get("symbol", "") or "").zfill(6) != symbol:
            continue
        trade_date = _parse_date(_record_date(trade))
        if start is None or trade_date is None:
            continue
        delta_days = (trade_date - start).days
        if 0 <= delta_days <= max(int(lookahead_days), 0):
            return index
    return None


def _linked_by(approval: dict[str, Any], trade: dict[str, Any] | None) -> str:
    if not trade:
        return ""
    if str(trade.get("order_approval_created_at", "") or "") == str(approval.get("created_at", "") or ""):
        return "approval_id"
    return "fallback_symbol_date"


def _strategy_from(approval: dict[str, Any], trade: dict[str, Any] | None) -> str:
    if trade and trade.get("strategy"):
        return str(trade.get("strategy", "") or "")
    if approval.get("strategy"):
        return str(approval.get("strategy", "") or "")
    pretrade = dict(approval.get("pretrade") or {})
    candidate = dict(pretrade.get("candidate_snapshot") or {})
    return str(pretrade.get("strategy") or candidate.get("strategy") or "")


def _trade_looks_planned(trade: dict[str, Any]) -> bool:
    return bool(
        trade.get("order_approval_created_at")
        or trade.get("execution_confirmation_created_at")
        or trade.get("planned_price")
        or trade.get("planned_pct")
        or trade.get("gate_status")
    )


def _trade_value(trade: dict[str, Any]) -> float:
    amount = _float_or_none(trade.get("amount"))
    if amount is not None:
        return amount
    return float(trade.get("price", 0) or 0) * int(trade.get("quantity", 0) or 0)


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
    approved_not_executed_count: int,
    missing_approval_trade_count: int,
    block_approval_executed_count: int,
    fallback_link_count: int,
    block_count: int,
    warn_count: int,
) -> list[str]:
    items: list[str] = []
    if block_approval_executed_count:
        items.append("Block approval was executed; freeze new BUY orders until the violation is reviewed.")
    if missing_approval_trade_count:
        items.append("BUY trades without final approval exist; require `portfolio approve --record` before every manual order.")
    if fallback_link_count:
        items.append("Some trades were matched only by symbol/date; attach `--order-approval` when recording fills.")
    if approved_not_executed_count:
        items.append("Approved orders were not executed or not recorded; mark whether they were cancelled, skipped, or missing from the trade log.")
    if block_count and not block_approval_executed_count:
        items.append("Blocking execution deviations exist; review size/value mismatches before increasing risk.")
    if warn_count and not block_count:
        items.append("Warnings exist; tighten fill recording and manual acceptance notes.")
    if not items:
        items.append("Approval-to-trade chain is clean in the current sample.")
    return items


def _pct(value: object) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.2%}"
