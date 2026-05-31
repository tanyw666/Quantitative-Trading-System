from __future__ import annotations


def render_discipline_adherence_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("total", 0) or 0) == 0:
        return ["- 暂无纪律执行跟踪记录。先持久化纪律建议，并记录后续交易。"]

    lines = [
        f"- 已检查记录：{int(summary.get('total', 0) or 0)}",
        f"- 纪律执行率：{float(summary.get('adherence_rate', 0) or 0):.1%}",
        f"- 通过/预警/阻断：{int(summary.get('pass_count', 0) or 0)} / {int(summary.get('warn_count', 0) or 0)} / {int(summary.get('block_count', 0) or 0)}",
        f"- 违规数：{int(summary.get('violation_count', 0) or 0)}",
        f"- 已说明例外：{int(summary.get('exception_count', 0) or 0)}",
    ]
    top_violation = _top_item(summary.get("by_violation", {}))
    if top_violation:
        lines.append(f"- 高频违规：{top_violation[0]}（{top_violation[1]}）")

    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(
            [
                "",
                "| 日期 | 来源 | 规则 | 检查窗口 | 结果 | 买入数 | 例外数 | 违规项 |",
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
    return "\n".join(["# 纪律执行跟踪", "", *render_discipline_adherence_lines(summary), ""])


def _top_item(values: dict | None) -> tuple[str, int] | None:
    items = [(str(key), int(value)) for key, value in (values or {}).items() if str(key)]
    if not items:
        return None
    return sorted(items, key=lambda item: (-item[1], item[0]))[0]


def _join(values: object) -> str:
    if not isinstance(values, list):
        return str(values or "")
    return ", ".join(str(item) for item in values if str(item))
