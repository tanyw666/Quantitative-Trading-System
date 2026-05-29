from __future__ import annotations

from quant_system.optimizer.health_labels import alert_reasons_text


def render_constraint_summary_lines(summary: dict | None, limit: int = 5) -> list[str]:
    if not summary or int(summary.get("total", 0) or 0) == 0:
        return ["- 暂无策略约束触发记录。"]

    lines = [
        f"- 触发次数：{int(summary.get('total', 0))}",
        f"- 预警/阻断：{int(summary.get('warn_count', 0))} / {int(summary.get('block_count', 0))}",
    ]
    top_strategy = _top_item(summary.get("by_strategy", {}))
    if top_strategy:
        lines.append(f"- 高频策略：{top_strategy[0]}（{top_strategy[1]}次）")
    top_alert = _top_item(summary.get("by_alert", {}))
    if top_alert:
        lines.append(f"- 主要触发原因：{alert_reasons_text([top_alert[0]])}（{top_alert[1]}次）")
    if summary.get("latest_created_at"):
        lines.append(f"- 最近触发：{summary.get('latest_created_at')}")
    trend_lines = _trend_lines(summary.get("trend"))
    if trend_lines:
        lines.extend(trend_lines)

    records = list(summary.get("records", []) or [])[-limit:]
    if records:
        lines.extend(["", "| 时间 | 来源 | 策略 | 级别 | 动作 | 原因 |", "| --- | --- | --- | --- | --- | --- |"])
        for record in records:
            lines.append(
                f"| {record.get('created_at', '')} | "
                f"{record.get('source', '')} | "
                f"{record.get('strategy', '')} | "
                f"{_alert_level_label(str(record.get('alert_level', '')))} | "
                f"{_action_label(str(record.get('action', '')))} | "
                f"{alert_reasons_text(record.get('alerts', []))} |"
            )
    return lines


def _top_item(values: dict | None) -> tuple[str, int] | None:
    items = [(str(key), int(value)) for key, value in (values or {}).items() if str(key)]
    if not items:
        return None
    return sorted(items, key=lambda item: (-item[1], item[0]))[0]


def _alert_level_label(level: str) -> str:
    return {"warn": "预警", "block": "阻断", "pass": "正常"}.get(level, level)


def _action_label(action: str) -> str:
    return {"increase": "提高优先级", "keep": "保持观察", "reduce": "降低仓位/暂停", "pause": "暂停策略"}.get(action, action)


def _trend_lines(trend: dict | None) -> list[str]:
    windows = (trend or {}).get("windows", {}) if isinstance(trend, dict) else {}
    lines: list[str] = []
    for key in ("5", "10"):
        item = windows.get(key)
        if not item:
            continue
        top_strategy = item.get("top_strategy")
        suffix = f"，高频策略 {top_strategy}" if top_strategy else ""
        lines.append(
            f"- 近{key}日趋势：触发 {int(item.get('total', 0))} 次，"
            f"预警 {int(item.get('warn_count', 0))} 次，"
            f"阻断 {int(item.get('block_count', 0))} 次{suffix}。"
        )
    return lines
