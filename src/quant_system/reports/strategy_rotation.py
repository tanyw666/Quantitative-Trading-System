from __future__ import annotations

from collections import Counter

from quant_system.optimizer.health_labels import alert_reasons_text
from quant_system.reports.trade_plan_pressure import format_trade_plan_pressure, normalize_trade_plan_pressure


def build_strategy_rotation(
    strategy_health: list[dict] | None,
    constraint_summary: dict | None = None,
    promotion_summary: dict | None = None,
    limit: int = 5,
) -> list[dict]:
    health_items = list(strategy_health or [])
    if not health_items:
        return []

    constraints = _constraint_counts_by_strategy(constraint_summary)
    has_backtest_promotion = bool((promotion_summary or {}).get("best_backtest"))
    rows: list[dict] = []
    for index, item in enumerate(health_items):
        strategy = str(item.get("strategy", "") or "")
        constraint_counts = constraints.get(strategy, Counter())
        score = float(item.get("score", 0) or 0)
        reasons: list[str] = []

        action = str(item.get("action", "") or "")
        alert_level = str(item.get("alert_level", "pass") or "pass")
        policy_state = str(item.get("policy_state", "") or "")
        if action == "increase":
            score += 8
            reasons.append("健康度建议提高优先级")
        elif action == "reduce":
            score -= 12
            reasons.append("健康度建议降权")
        elif action == "pause":
            score -= 35
            reasons.append("健康度建议暂停")

        if alert_level == "warn":
            score -= 10
            reasons.append("存在预警")
        elif alert_level == "block":
            score -= 25
            reasons.append("存在阻断")
        if policy_state in {"blocked", "cooldown"}:
            score -= 15
            reasons.append("处于冷静期/阻断规则")
        elif policy_state in {"watch", "repeated_warn"}:
            score -= 6
            reasons.append("处于恢复观察")

        pressure = normalize_trade_plan_pressure(item)
        match_rate = float(pressure.get("match_rate", 0) or 0) if pressure else 0.0
        unmatched_plans = int(pressure.get("unmatched_plans", 0) or 0) if pressure else 0
        orphan_trades = int(pressure.get("orphan_trades", 0) or 0) if pressure else 0
        avg_price_deviation_pct = float(pressure.get("avg_price_deviation_pct", 0) or 0) if pressure else 0.0
        if pressure:
            reasons.append(f"计划压力：{format_trade_plan_pressure(pressure)}")
        if match_rate > 0 or unmatched_plans > 0 or orphan_trades > 0:
            if match_rate < 0.7 or unmatched_plans >= 3 or orphan_trades >= 2:
                score -= 28
                reasons.append("计划-成交失配严重")
                if policy_state in {"blocked", "cooldown"} or alert_level == "block":
                    score -= 8
                    reasons.append("失配叠加阻断状态")
            elif match_rate < 0.85 or unmatched_plans > 0 or orphan_trades > 0 or abs(avg_price_deviation_pct) > 0.03:
                score -= 12
                reasons.append("计划-成交存在漂移")
                if policy_state in {"watch", "repeated_warn"} or alert_level == "warn":
                    score -= 4
                    reasons.append("漂移叠加预警状态")
        elif abs(avg_price_deviation_pct) > 0.03:
            score -= 8
            reasons.append("执行偏差偏大")

        lifecycle_pressure = item.get("lifecycle_pressure") or {}
        if lifecycle_pressure:
            lifecycle_score = float(lifecycle_pressure.get("score", 100) or 100)
            lifecycle_action = str(lifecycle_pressure.get("action", "keep") or "keep")
            lifecycle_level = str(lifecycle_pressure.get("alert_level", "pass") or "pass")
            score -= min((100.0 - lifecycle_score) * 0.25, 15.0)
            if lifecycle_action == "pause" or lifecycle_level == "block":
                score -= 18
                reasons.append("生命周期闭环阻断")
            elif lifecycle_action == "reduce" or lifecycle_level == "warn":
                score -= 8
                reasons.append("生命周期闭环降档")

        warn_count = int(constraint_counts.get("warn", 0))
        block_count = int(constraint_counts.get("block", 0))
        if warn_count:
            score -= warn_count * 4
            reasons.append(f"近期预警 {warn_count} 次")
        if block_count:
            score -= block_count * 12
            reasons.append(f"近期阻断 {block_count} 次")

        if has_backtest_promotion and index == 0:
            score += 4
            reasons.append("近期有晋级/回测记录辅助")
        if item.get("alerts"):
            reasons.append(f"告警：{alert_reasons_text(item.get('alerts', []))}")

        final_score = round(max(score, 0.0), 2)
        rows.append(
            {
                "strategy": strategy,
                "rotation_score": final_score,
                "priority": _priority(final_score, action, alert_level),
                "action": _rotation_action(final_score, action, alert_level),
                "health_score": float(item.get("score", 0) or 0),
                "alert_level": alert_level,
                "policy_state": policy_state,
                "recent_warn_count": warn_count,
                "recent_block_count": block_count,
                "trade_plan_match_rate": match_rate if match_rate > 0 else None,
                "trade_plan_unmatched_count": unmatched_plans,
                "trade_plan_orphan_count": orphan_trades,
                "trade_plan_avg_price_deviation_pct": avg_price_deviation_pct
                if match_rate > 0 or unmatched_plans > 0 or orphan_trades > 0
                else None,
                "lifecycle_pressure": lifecycle_pressure,
                "reasons": reasons[:4],
            }
        )
    return sorted(rows, key=lambda row: (-float(row.get("rotation_score", 0)), str(row.get("strategy", ""))))[:limit]


def render_strategy_rotation_lines(rotation: list[dict] | None) -> list[str]:
    if not rotation:
        return ["- 暂无策略轮换数据。"]

    lines = [
        "| 策略 | 轮换分 | 优先级 | 动作 | 预警 | 阻断 | 依据 |",
        "| --- | ---: | --- | --- | ---: | ---: | --- |",
    ]
    for item in rotation:
        lines.append(
            f"| {item.get('strategy', '')} | "
            f"{float(item.get('rotation_score', 0)):.1f} | "
            f"{item.get('priority', '')} | "
            f"{item.get('action', '')} | "
            f"{int(item.get('recent_warn_count', 0))} | "
            f"{int(item.get('recent_block_count', 0))} | "
            f"{'；'.join(item.get('reasons', []) or ['-'])} |"
        )
    leader = rotation[0]
    lines.append("")
    lines.append(f"- 当前主线建议：{leader.get('strategy', '')}，{leader.get('action', '')}。")
    pressure = normalize_trade_plan_pressure(leader)
    if pressure:
        lines.append(f"- 计划压力：{format_trade_plan_pressure(pressure)}")
    lifecycle_pressure = leader.get("lifecycle_pressure") or {}
    if lifecycle_pressure:
        summary = lifecycle_pressure.get("summary") or f"状态 {lifecycle_pressure.get('status', '-')}"
        lines.append(f"- 生命周期压力：{summary}")
    return lines


def _constraint_counts_by_strategy(summary: dict | None) -> dict[str, Counter]:
    counts: dict[str, Counter] = {}
    for record in (summary or {}).get("records", []) or []:
        strategy = str(record.get("strategy", "") or "")
        if not strategy:
            continue
        counts.setdefault(strategy, Counter())[str(record.get("alert_level", ""))] += 1
    return counts


def _priority(score: float, action: str, alert_level: str) -> str:
    if action == "pause" or alert_level == "block" or score < 45:
        return "暂停"
    if score >= 80:
        return "主打"
    if score >= 65:
        return "观察"
    return "轻仓"


def _rotation_action(score: float, action: str, alert_level: str) -> str:
    if action == "pause" or alert_level == "block" or score < 45:
        return "暂停新开仓，只复盘和处理持仓"
    if score >= 80:
        return "作为下个交易日主策略"
    if score >= 65:
        return "只做计划内确认单"
    return "小仓验证，不追高"
