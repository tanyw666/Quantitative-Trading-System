from __future__ import annotations

from typing import Any


def render_strategy_portfolio_lines(plan: dict[str, Any] | None) -> list[str]:
    if not plan:
        return ["- 未启用策略组合管理器。"]
    market = dict(plan.get("market_temperature") or {})
    sleeves = list(plan.get("sleeves") or [])
    lines = [
        f"- 组合：{plan.get('name', '')}",
        f"- 组合判定市场：{market.get('regime', '')}，温度 {float(market.get('score', 0) or 0):.1f}",
        "",
        "| 策略袖仓 | 角色 | 状态 | 预算 | 候选 | 动作依据 |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in sleeves:
        lines.append(
            f"| {item.get('name', '')} | "
            f"{item.get('role', '')} | "
            f"{item.get('status', '')} | "
            f"{float(item.get('budget_pct', 0) or 0):.1%} | "
            f"{int(item.get('selected_count', 0) or 0)} | "
            f"{item.get('reason', '')} |"
        )
    return lines
