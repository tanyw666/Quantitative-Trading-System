from __future__ import annotations


def render_discipline_summary_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("total", 0) or 0) == 0:
        return ["- No discipline records yet. Use --record-discipline to persist daily advice."]

    lines = [
        f"- Records: {int(summary.get('total', 0) or 0)}",
        f"- Pass/warn/block: {int(summary.get('pass_count', 0) or 0)} / {int(summary.get('warn_count', 0) or 0)} / {int(summary.get('block_count', 0) or 0)}",
    ]
    top_advice = _top_item(summary.get("top_advice", {}))
    if top_advice:
        lines.append(f"- Most repeated advice: {top_advice[0]} ({top_advice[1]})")
    latest = summary.get("latest_created_at")
    if latest:
        lines.append(f"- Latest record: {latest}")

    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(["", "| Date | Source | Status | Gate violations | Missing gates | Avg deviation | Holding | Exposure |", "| --- | --- | --- | ---: | ---: | ---: | --- | --- |"])
        for record in records:
            lines.append(
                f"| {record.get('date', '')} | "
                f"{record.get('source', '')} | "
                f"{record.get('status', '')} | "
                f"{int(record.get('gate_violation_count', 0) or 0)} | "
                f"{int(record.get('missing_gate_count', 0) or 0)} | "
                f"{float(record.get('avg_execution_deviation_pct', 0) or 0):.2%} | "
                f"{record.get('holding_status', '')} | "
                f"{float(record.get('allocated_pct', 0) or 0):.1%}/{float(record.get('target_exposure_pct', 0) or 0):.1%} |"
            )
    return lines


def _top_item(values: dict | None) -> tuple[str, int] | None:
    items = [(str(key), int(value)) for key, value in (values or {}).items() if str(key)]
    if not items:
        return None
    return sorted(items, key=lambda item: (-item[1], item[0]))[0]
