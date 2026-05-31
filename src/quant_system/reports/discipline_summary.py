from __future__ import annotations


def render_discipline_summary_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("total", 0) or 0) == 0:
        return ["- 暂无纪律记录。可使用 `--record-discipline` 持久化每日纪律建议。"]

    lines = [
        f"- 记录数：{int(summary.get('total', 0) or 0)}",
        f"- 通过/预警/阻断：{int(summary.get('pass_count', 0) or 0)} / {int(summary.get('warn_count', 0) or 0)} / {int(summary.get('block_count', 0) or 0)}",
    ]
    top_advice = _top_item(summary.get("top_advice", {}))
    if top_advice:
        lines.append(f"- 重复最多的建议：{top_advice[0]}（{top_advice[1]}）")
    latest = summary.get("latest_created_at")
    if latest:
        lines.append(f"- 最新记录：{latest}")

    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(["", "| 日期 | 来源 | 状态 | 门禁违规 | 缺失门禁 | 平均偏差 | 持仓状态 | 暴露 |", "| --- | --- | --- | ---: | ---: | ---: | --- | --- |"])
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
