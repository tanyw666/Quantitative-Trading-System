from __future__ import annotations


def render_gate_review_markdown(summary: dict) -> str:
    lines = [
        "# 门禁审计",
        "",
        *render_gate_review_lines(summary),
        "",
        "## 最近门禁记录",
        "",
    ]
    records = list(summary.get("latest_records", []) or [])
    if records:
        lines.extend(["| 日期 | 标的 | 方向 | 策略 | 状态 | 原因 |", "| --- | --- | --- | --- | --- | --- |"])
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
        lines.append("- 暂无门禁记录。")

    violations = list(summary.get("latest_violations", []) or [])
    lines.extend(["", "## 预警/阻断买入记录", ""])
    if violations:
        lines.extend(["| 日期 | 标的 | 策略 | 状态 | 信息 |", "| --- | --- | --- | --- | --- |"])
        for record in violations:
            lines.append(
                f"| {record.get('date', '')} | "
                f"{_symbol_label(record)} | "
                f"{record.get('strategy', '')} | "
                f"{_status_label(str(record.get('status', '')))} | "
                f"{record.get('message', '')} |"
            )
    else:
        lines.append("- 暂无预警或阻断买入记录。")
    return "\n".join(lines)


def render_gate_review_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("gate_record_count", 0) or 0) == 0:
        return ["- 暂无门禁记录。开始交易前，请把 workflow 门禁上下文写入每笔交易。"]

    lines = [
        f"- 已扫描交易：{int(summary.get('total_trades', 0) or 0)}",
        f"- 门禁记录：{int(summary.get('gate_record_count', 0) or 0)}",
        f"- 缺失门禁快照：{int(summary.get('missing_gate_count', 0) or 0)}",
        f"- 买入违规率：{float(summary.get('violation_rate', 0) or 0):.1%}",
        f"- 预警/阻断买入数：{int(summary.get('violation_count', 0) or 0)}",
    ]

    status_counts = summary.get("status_counts", {}) or {}
    if status_counts:
        lines.append(
            "- 状态分布："
            + ", ".join(f"{_status_label(str(key))}={int(value)}" for key, value in sorted(status_counts.items()))
        )
    buy_status_counts = summary.get("buy_status_counts", {}) or {}
    if buy_status_counts:
        lines.append(
            "- 买入状态分布："
            + ", ".join(f"{_status_label(str(key))}={int(value)}" for key, value in sorted(buy_status_counts.items()))
        )

    top_reason = _top_item(summary.get("by_reason", {}))
    if top_reason:
        lines.append(f"- 高频原因：{top_reason[0]}（{top_reason[1]}）")
    top_strategy = _top_item(summary.get("by_strategy", {}))
    if top_strategy:
        lines.append(f"- 高频策略：{top_strategy[0]}（{top_strategy[1]}）")
    top_symbol = _top_item(summary.get("by_symbol", {}))
    if top_symbol:
        lines.append(f"- 高频标的：{top_symbol[0]}（{top_symbol[1]}）")

    action_items = list(summary.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "## 行动项", ""])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def _top_item(values: dict | None) -> tuple[str, int] | None:
    items = [(str(key), int(value)) for key, value in (values or {}).items() if str(key)]
    if not items:
        return None
    return sorted(items, key=lambda item: (-item[1], item[0]))[0]


def _status_label(status: str) -> str:
    return {"pass": "通过", "warn": "预警", "block": "阻断"}.get(status, status or "未知")


def _symbol_label(record: dict) -> str:
    label = f"{record.get('symbol', '')} {record.get('name', '')}".strip()
    return label or "-"


def _join(values: object) -> str:
    if not isinstance(values, list):
        return str(values or "")
    return ", ".join(str(item) for item in values if str(item))
