from __future__ import annotations

from quant_system.portfolio.trade_plan import render_trade_plan_summary_markdown, summarize_trade_plan_records


def render_trade_plan_summary_lines(summary: dict | None) -> list[str]:
    if not summary:
        return ["- 暂无交易计划单记录。"]
    records = list(summary.get("records", []) or [])
    lines = [
        f"- 记录数：{int(summary.get('total', 0) or 0)}",
        f"- 通过/警告/阻断：{int(summary.get('pass_count', 0) or 0)} / {int(summary.get('warn_count', 0) or 0)} / {int(summary.get('block_count', 0) or 0)}",
        f"- 计划总额：{float(summary.get('planned_value', 0) or 0):.2f}",
        f"- 可用总额：{float(summary.get('allowed_value', 0) or 0):.2f}",
    ]
    if records:
        for record in records[-5:]:
            lines.append(
                f"- {record.get('trade_date', record.get('date', ''))} {record.get('symbol', '')} "
                f"{record.get('gate_status', '')} {float(record.get('planned_pct', 0) or 0):.1%}"
            )
    return lines


def build_trade_plan_summary(records: list[dict], limit: int = 20) -> dict:
    return summarize_trade_plan_records(records, limit=limit)


def render_trade_plan_summary_markdown_block(summary: dict | None) -> str:
    return render_trade_plan_summary_markdown(summary)
