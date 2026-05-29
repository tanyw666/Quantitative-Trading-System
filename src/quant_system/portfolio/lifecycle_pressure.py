from __future__ import annotations

from typing import Any


def build_lifecycle_pressure(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {}

    execution = snapshot.get("execution", {}) or {}
    lots = snapshot.get("lots", {}) or {}
    holding = snapshot.get("holding_actions", {}) or {}
    exit_plan = snapshot.get("exit_plan", {}) or {}
    status = str(snapshot.get("status", "pass") or "pass")

    alerts: list[str] = []
    score = 100.0
    action = "keep"
    alert_level = "pass"

    missed_actions = int(execution.get("action_missed_count", 0) or 0)
    missed_exits = int(execution.get("exit_missed_count", 0) or 0)
    missed_lot_exits = int(execution.get("lot_exit_missed_count", 0) or 0)
    sell_all_count = int(exit_plan.get("sell_all_count", 0) or 0)
    stale_lots = int(lots.get("stale_open_lots", 0) or 0)
    reduce_count = int(holding.get("reduce_count", 0) or 0)
    exit_count = int(holding.get("exit_count", 0) or 0)

    if status == "block" or missed_actions or missed_exits or missed_lot_exits or sell_all_count:
        alert_level = "block"
        action = "pause"
        alerts.append("lifecycle_block")
        score -= 25.0
        score -= min((missed_actions + missed_exits + missed_lot_exits) * 8.0, 24.0)
        score -= min(sell_all_count * 6.0, 18.0)
    elif status == "warn" or stale_lots or reduce_count or exit_count:
        alert_level = "warn"
        action = "reduce"
        alerts.append("lifecycle_drift")
        score -= 12.0
        score -= min(stale_lots * 4.0 + reduce_count * 3.0 + exit_count * 5.0, 18.0)

    score = _apply_rate_pressure(
        score,
        execution,
        "action_execution_rate",
        "action_actionable_count",
        alerts,
        "action_execution_gap",
    )
    score = _apply_rate_pressure(
        score,
        execution,
        "exit_execution_rate",
        "exit_actionable_count",
        alerts,
        "exit_execution_gap",
    )
    score = _apply_rate_pressure(
        score,
        execution,
        "lot_exit_execution_rate",
        "lot_exit_actionable_count",
        alerts,
        "lot_exit_execution_gap",
    )

    if any(alert in alerts for alert in ("action_execution_gap", "exit_execution_gap", "lot_exit_execution_gap")):
        if alert_level == "pass":
            alert_level = "warn"
        if action == "keep":
            action = "reduce"

    return {
        "status": status,
        "score": round(max(score, 0.0), 2),
        "alert_level": alert_level,
        "action": action,
        "alerts": _unique(alerts),
        "stale_open_lots": stale_lots,
        "exit_count": exit_count,
        "reduce_count": reduce_count,
        "sell_all_count": sell_all_count,
        "trade_plan_match_rate": _float(execution.get("trade_plan_match_rate")),
        "action_execution_rate": _float(execution.get("action_execution_rate")),
        "exit_execution_rate": _float(execution.get("exit_execution_rate")),
        "lot_exit_execution_rate": _float(execution.get("lot_exit_execution_rate")),
        "action_missed_count": missed_actions,
        "exit_missed_count": missed_exits,
        "lot_exit_missed_count": missed_lot_exits,
        "summary": lifecycle_pressure_summary(snapshot),
    }


def lifecycle_pressure_summary(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return ""
    execution = snapshot.get("execution", {}) or {}
    lots = snapshot.get("lots", {}) or {}
    exit_plan = snapshot.get("exit_plan", {}) or {}
    status = str(snapshot.get("status", "pass") or "pass")
    return (
        f"状态 {status}；计划命中 {float(execution.get('trade_plan_match_rate', 0) or 0):.1%}；"
        f"动作执行 {float(execution.get('action_execution_rate', 0) or 0):.1%}；"
        f"退出执行 {float(execution.get('exit_execution_rate', 0) or 0):.1%}；"
        f"批次退出 {float(execution.get('lot_exit_execution_rate', 0) or 0):.1%}；"
        f"陈旧批次 {int(lots.get('stale_open_lots', 0) or 0)}；"
        f"清仓任务 {int(exit_plan.get('sell_all_count', 0) or 0)}"
    )


def _apply_rate_pressure(
    score: float,
    execution: dict[str, Any],
    rate_key: str,
    count_key: str,
    alerts: list[str],
    alert: str,
) -> float:
    actionable_count = int(execution.get(count_key, 0) or 0)
    if actionable_count <= 0:
        return score
    rate = float(execution.get(rate_key, 0) or 0)
    if rate >= 1.0:
        return score
    alerts.append(alert)
    return score - min((1.0 - rate) * 20.0, 12.0)


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result
