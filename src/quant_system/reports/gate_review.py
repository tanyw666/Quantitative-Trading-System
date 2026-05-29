from __future__ import annotations


def render_gate_review_markdown(summary: dict) -> str:
    lines = [
        "# Gate Review",
        "",
        *render_gate_review_lines(summary),
        "",
        "## Recent Gate Records",
        "",
    ]
    records = list(summary.get("latest_records", []) or [])
    if records:
        lines.extend(["| Date | Symbol | Side | Strategy | Status | Reasons |", "| --- | --- | --- | --- | --- | --- |"])
        for record in records:
            lines.append(
                f"| {record.get('date', '')} | "
                f"{_symbol_label(record)} | "
                f"{record.get('side', '')} | "
                f"{record.get('strategy', '')} | "
                f"{_status_label(str(record.get('status', '')))} | "
                f"{_join(record.get('reasons', []))} |"
            )
    else:
        lines.append("- No gate records.")

    violations = list(summary.get("latest_violations", []) or [])
    lines.extend(["", "## Warn/Block BUY Records", ""])
    if violations:
        lines.extend(["| Date | Symbol | Strategy | Status | Message |", "| --- | --- | --- | --- | --- |"])
        for record in violations:
            lines.append(
                f"| {record.get('date', '')} | "
                f"{_symbol_label(record)} | "
                f"{record.get('strategy', '')} | "
                f"{_status_label(str(record.get('status', '')))} | "
                f"{record.get('message', '')} |"
            )
    else:
        lines.append("- No warn/block BUY records.")
    return "\n".join(lines)


def render_gate_review_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("gate_record_count", 0) or 0) == 0:
        return ["- No gate records yet. Start by attaching workflow gate context to each trade."]

    lines = [
        f"- Trades scanned: {int(summary.get('total_trades', 0) or 0)}",
        f"- Gate records: {int(summary.get('gate_record_count', 0) or 0)}",
        f"- Missing gate snapshots: {int(summary.get('missing_gate_count', 0) or 0)}",
        f"- BUY violation rate: {float(summary.get('violation_rate', 0) or 0):.1%}",
        f"- Warn/block BUY count: {int(summary.get('violation_count', 0) or 0)}",
    ]

    status_counts = summary.get("status_counts", {}) or {}
    if status_counts:
        lines.append(
            "- Status mix: "
            + ", ".join(f"{_status_label(str(key))}={int(value)}" for key, value in sorted(status_counts.items()))
        )
    buy_status_counts = summary.get("buy_status_counts", {}) or {}
    if buy_status_counts:
        lines.append(
            "- BUY status mix: "
            + ", ".join(f"{_status_label(str(key))}={int(value)}" for key, value in sorted(buy_status_counts.items()))
        )

    top_reason = _top_item(summary.get("by_reason", {}))
    if top_reason:
        lines.append(f"- Top reason: {top_reason[0]} ({top_reason[1]})")
    top_strategy = _top_item(summary.get("by_strategy", {}))
    if top_strategy:
        lines.append(f"- Most frequent strategy: {top_strategy[0]} ({top_strategy[1]})")
    top_symbol = _top_item(summary.get("by_symbol", {}))
    if top_symbol:
        lines.append(f"- Most frequent symbol: {top_symbol[0]} ({top_symbol[1]})")

    action_items = list(summary.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def _top_item(values: dict | None) -> tuple[str, int] | None:
    items = [(str(key), int(value)) for key, value in (values or {}).items() if str(key)]
    if not items:
        return None
    return sorted(items, key=lambda item: (-item[1], item[0]))[0]


def _status_label(status: str) -> str:
    return {"pass": "pass", "warn": "warn", "block": "block"}.get(status, status or "unknown")


def _symbol_label(record: dict) -> str:
    label = f"{record.get('symbol', '')} {record.get('name', '')}".strip()
    return label or "-"


def _join(values: object) -> str:
    if not isinstance(values, list):
        return str(values or "")
    return ", ".join(str(item) for item in values if str(item))
