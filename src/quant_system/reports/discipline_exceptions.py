from __future__ import annotations


def render_discipline_exception_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("exception_count", 0) or 0) == 0:
        return ["- No discipline exceptions recorded."]

    lines = [
        f"- Trades scanned: {int(summary.get('total_trades', 0) or 0)}",
        f"- Exception count: {int(summary.get('exception_count', 0) or 0)}",
        f"- Approved / missing reason: {int(summary.get('approved_exception_count', 0) or 0)} / {int(summary.get('missing_reason_count', 0) or 0)}",
        f"- Exception rate: {float(summary.get('exception_rate', 0) or 0):.1%}",
    ]
    top_strategy = _top_item(summary.get("by_strategy", {}))
    if top_strategy:
        lines.append(f"- Top strategy: {top_strategy[0]} ({top_strategy[1]})")
    top_symbol = _top_item(summary.get("by_symbol", {}))
    if top_symbol:
        lines.append(f"- Top symbol: {top_symbol[0]} ({top_symbol[1]})")

    action_items = list(summary.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in action_items)

    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(["", "| Date | Symbol | Side | Strategy | Gate | Reason |", "| --- | --- | --- | --- | --- | --- |"])
        for record in records:
            lines.append(
                f"| {record.get('date', '')} | "
                f"{_symbol_label(record)} | "
                f"{record.get('side', '')} | "
                f"{record.get('strategy', '')} | "
                f"{record.get('gate_status', '')} | "
                f"{record.get('exception_reason', '')} |"
            )
    return lines


def render_discipline_exception_markdown(summary: dict | None) -> str:
    return "\n".join(["# Discipline Exceptions", "", *render_discipline_exception_lines(summary), ""])


def _top_item(values: dict | None) -> tuple[str, int] | None:
    items = [(str(key), int(value)) for key, value in (values or {}).items() if str(key)]
    if not items:
        return None
    return sorted(items, key=lambda item: (-item[1], item[0]))[0]


def _symbol_label(record: dict) -> str:
    label = f"{record.get('symbol', '')} {record.get('name', '')}".strip()
    return label or "-"
