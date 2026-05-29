from __future__ import annotations

from quant_system.optimizer.health_labels import alert_reasons_text
from quant_system.reports.trade_plan_pressure import format_trade_plan_pressure, normalize_trade_plan_pressure


def render_action_advice_lines(
    *,
    strategy_health: list[dict] | None = None,
    constraint_summary: dict | None = None,
    trade_plan_audit: dict | None = None,
    allocation_plan: dict | None = None,
    market_temperature: dict | None = None,
    holding_action_plan: dict | None = None,
    exit_plan: dict | None = None,
) -> list[str]:
    lines: list[str] = []
    leader = _leader(strategy_health)
    latest_constraint = _latest_constraint(constraint_summary)
    trade_plan_pressure = normalize_trade_plan_pressure(trade_plan_audit, latest_constraint, leader)
    alert_level = str((latest_constraint or leader or {}).get("alert_level", "pass") or "pass")
    action = str((leader or latest_constraint or {}).get("action", "") or "")

    if alert_level == "block" or action == "pause":
        strategy = str((latest_constraint or leader or {}).get("strategy", "") or "当前策略")
        alerts = (latest_constraint or leader or {}).get("alerts", []) or []
        lines.append(f"- {strategy} 明日进入暂停观察：不新增仓位，只允许处理已有持仓风险。触发：{alert_reasons_text(alerts)}。")
    elif alert_level == "warn":
        strategy = str((latest_constraint or leader or {}).get("strategy", "") or "当前策略")
        alerts = (latest_constraint or leader or {}).get("alerts", []) or []
        lines.append(f"- {strategy} 明日降半档执行：只做计划内低吸/确认单，禁止追高加速。触发：{alert_reasons_text(alerts)}。")
    elif leader:
        lines.append(f"- 优先跟踪 {leader.get('strategy', '')}：评分 {float(leader.get('score', 0)):.1f}，动作 {_action_label(str(leader.get('action', '')))}。")
    else:
        lines.append("- 暂无策略健康度约束，明日按市场温度和仓位计划执行。")

    policy = (leader or {}).get("constraint_policy") or {}
    if policy.get("note"):
        lines.append(f"- 恢复/冷静期规则：{policy.get('note')}")

    if trade_plan_pressure:
        lines.append(f"- 计划压力：{format_trade_plan_pressure(trade_plan_pressure)}")

    lifecycle_pressure = (leader or {}).get("lifecycle_pressure") or {}
    if lifecycle_pressure:
        summary = lifecycle_pressure.get("summary") or f"状态 {lifecycle_pressure.get('status', '-')}"
        lines.append(f"- 生命周期压力：{summary}")

    if allocation_plan:
        if allocation_plan.get("strategy_adjustment_note"):
            lines.append(f"- 仓位约束：{allocation_plan.get('strategy_adjustment_note')}")
        target = float(allocation_plan.get("target_exposure_pct", 0) or 0)
        allocated = float(allocation_plan.get("allocated_pct", 0) or 0)
        lines.append(f"- 明日总仓位参考：目标 {target:.1%}，当前计划分配 {allocated:.1%}。")

    if market_temperature:
        regime = str(market_temperature.get("regime", "") or "")
        stance = str(market_temperature.get("stance", "") or "")
        if regime in {"cold", "frozen", "empty"}:
            lines.append("- 市场温度偏低，候选再强也先降频验证，等待放量和板块确认。")
        elif stance:
            lines.append(f"- 市场动作基准：{stance}。")

    if holding_action_plan:
        exit_count = int(holding_action_plan.get("exit_count", 0) or 0)
        reduce_count = int(holding_action_plan.get("reduce_count", 0) or 0)
        watch_count = int(holding_action_plan.get("watch_count", 0) or 0)
        if exit_count or reduce_count or watch_count:
            lines.append(f"- 持仓动作：清仓 {exit_count}，减仓 {reduce_count}，观察 {watch_count}。")
        top_action = next(
            (
                item
                for item in list(holding_action_plan.get("actions", []) or [])
                if str(item.get("action", "") or "") in {"exit", "reduce", "watch"}
            ),
            None,
        )
        if top_action:
            lines.append(
                f"- 首要处理：{top_action.get('symbol', '')} {top_action.get('action', '')}，原因：{top_action.get('reason', '')}"
            )

    lines.append("- 买入前必须再跑 precheck；实际成交后写入交易日志，盘后检查执行偏差。")
    if exit_plan:
        sell_all_count = int(exit_plan.get("sell_all_count", 0) or 0)
        take_profit_count = int(exit_plan.get("take_profit_count", 0) or 0)
        reduce_count = int(exit_plan.get("reduce_count", 0) or 0)
        if sell_all_count or take_profit_count or reduce_count:
            lines.append(f"- Exit plan focus: sell all {sell_all_count}, take profit {take_profit_count}, reduce {reduce_count}.")
    return lines


def _leader(strategy_health: list[dict] | None) -> dict | None:
    return strategy_health[0] if strategy_health else None


def _latest_constraint(summary: dict | None) -> dict | None:
    records = list((summary or {}).get("records", []) or [])
    return records[-1] if records else None


def _action_label(action: str) -> str:
    return {
        "increase": "提高优先级",
        "keep": "保持观察",
        "reduce": "降低仓位/暂缓",
        "pause": "暂停策略",
    }.get(action, action or "保持观察")
