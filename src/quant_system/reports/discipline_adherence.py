from __future__ import annotations


def render_discipline_adherence_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("total", 0) or 0) == 0:
        return ["- No discipline adherence records yet. Persist discipline advice and record follow-up trades first."]

    lines = [
        f"- Records checked: {int(summary.get('total', 0) or 0)}",
        f"- Adherence rate: {float(summary.get('adherence_rate', 0) or 0):.1%}",
        f"- Pass/warn/block: {int(summary.get('pass_count', 0) or 0)} / {int(summary.get('warn_count', 0) or 0)} / {int(summary.get('block_count', 0) or 0)}",
        f"- Violations: {int(summary.get('violation_count', 0) or 0)}",
        f"- Documented exceptions: {int(summary.get('exception_count', 0) or 0)}",
    ]
    top_violation = _top_item(summary.get("by_violation", {}))
    if top_violation:
        lines.append(f"- Top violation: {top_violation[0]} ({top_violation[1]})")

    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(
            [
                "",
                "| Date | Source | Rule | Window | Result | BUYs | Exceptions | Violations |",
                "| --- | --- | --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for record in records:
            window = f"{record.get('applicable_start', '')}..{record.get('applicable_end', '')}"
            lines.append(
                f"| {record.get('date', '')} | "
                f"{record.get('source', '')} | "
                f"{record.get('status', '')} | "
                f"{window} | "
                f"{record.get('adherence_status', '')} | "
                f"{int(record.get('buy_count_next_window', 0) or 0)} | "
                f"{int(record.get('approved_exception_count', 0) or 0)} | "
                f"{_join(record.get('violations', []))} |"
            )
    return lines


def render_discipline_adherence_markdown(summary: dict | None) -> str:
    return "\n".join(["# Discipline Adherence", "", *render_discipline_adherence_lines(summary), ""])


def _top_item(values: dict | None) -> tuple[str, int] | None:
    items = [(str(key), int(value)) for key, value in (values or {}).items() if str(key)]
    if not items:
        return None
    return sorted(items, key=lambda item: (-item[1], item[0]))[0]


def _join(values: object) -> str:
    if not isinstance(values, list):
        return str(values or "")
    return ", ".join(str(item) for item in values if str(item))
