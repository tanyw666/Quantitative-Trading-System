from __future__ import annotations

from typing import Any


def build_position_lifecycle_snapshot(
    *,
    trade_plan_summary: dict | None = None,
    lot_book: dict | None = None,
    holding_action_plan: dict | None = None,
    exit_plan: dict | None = None,
    lifecycle_rule_plan: dict | None = None,
    trade_plan_audit: dict | None = None,
    action_execution_summary: dict | None = None,
    exit_execution_summary: dict | None = None,
    lot_exit_execution_summary: dict | None = None,
) -> dict[str, Any]:
    return {
        "trade_plan": _trade_plan_snapshot(trade_plan_summary),
        "lots": _lot_snapshot(lot_book),
        "holding_actions": _holding_action_snapshot(holding_action_plan),
        "exit_plan": _exit_plan_snapshot(exit_plan),
        "lifecycle_rules": _lifecycle_rule_snapshot(lifecycle_rule_plan),
        "execution": _execution_snapshot(
            trade_plan_audit=trade_plan_audit,
            action_execution_summary=action_execution_summary,
            exit_execution_summary=exit_execution_summary,
            lot_exit_execution_summary=lot_exit_execution_summary,
        ),
        "status": _rollup_status(
            trade_plan_summary=trade_plan_summary,
            lot_book=lot_book,
            holding_action_plan=holding_action_plan,
            exit_plan=exit_plan,
            lifecycle_rule_plan=lifecycle_rule_plan,
            trade_plan_audit=trade_plan_audit,
            action_execution_summary=action_execution_summary,
            exit_execution_summary=exit_execution_summary,
            lot_exit_execution_summary=lot_exit_execution_summary,
        ),
    }


def render_position_lifecycle_lines(snapshot: dict | None) -> list[str]:
    if not snapshot:
        return ["- 暂无持仓生命周期快照。"]
    trade_plan = snapshot.get("trade_plan", {}) or {}
    lots = snapshot.get("lots", {}) or {}
    holding = snapshot.get("holding_actions", {}) or {}
    exit_plan = snapshot.get("exit_plan", {}) or {}
    lifecycle_rules = snapshot.get("lifecycle_rules", {}) or {}
    execution = snapshot.get("execution", {}) or {}
    lines = [
        f"- 状态：{snapshot.get('status', 'pass')}",
        f"- 买入计划：{int(trade_plan.get('records', 0) or 0)} 条，计划金额 {float(trade_plan.get('planned_value', 0) or 0):.2f}，可用金额 {float(trade_plan.get('allowed_value', 0) or 0):.2f}",
        f"- 持仓批次：开仓 {int(lots.get('open_lots', 0) or 0)}，陈旧 {int(lots.get('stale_open_lots', 0) or 0)}，浮盈亏 {float(lots.get('open_unrealized_pnl', 0) or 0):.2f}",
        f"- 持仓动作：清仓 {int(holding.get('exit_count', 0) or 0)}，减仓 {int(holding.get('reduce_count', 0) or 0)}，观察 {int(holding.get('watch_count', 0) or 0)}",
        f"- 退出计划：清仓 {int(exit_plan.get('sell_all_count', 0) or 0)}，止盈 {int(exit_plan.get('take_profit_count', 0) or 0)}，时限止损 {int(exit_plan.get('time_stop_count', 0) or 0)}",
        f"- 执行情况：计划命中 {float(execution.get('trade_plan_match_rate', 0) or 0):.1%}，动作执行 {float(execution.get('action_execution_rate', 0) or 0):.1%}，退出执行 {float(execution.get('exit_execution_rate', 0) or 0):.1%}，分批退出执行 {float(execution.get('lot_exit_execution_rate', 0) or 0):.1%}",
    ]
    lines.append(
        f"- Lifecycle rules: add {int(lifecycle_rules.get('add_count', 0) or 0)}, "
        f"reduce {int(lifecycle_rules.get('reduce_count', 0) or 0)}, "
        f"blocked-add {int(lifecycle_rules.get('blocked_add_count', 0) or 0)}"
    )
    action_items = lifecycle_action_items(snapshot)
    if action_items:
        lines.extend(["", "行动项："])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def render_position_lifecycle_markdown(snapshot: dict | None) -> str:
    return "\n".join(["# 持仓生命周期", "", *render_position_lifecycle_lines(snapshot), ""])


def lifecycle_action_items(snapshot: dict) -> list[str]:
    status = str(snapshot.get("status", "pass") or "pass")
    lots = snapshot.get("lots", {}) or {}
    exit_plan = snapshot.get("exit_plan", {}) or {}
    lifecycle_rules = snapshot.get("lifecycle_rules", {}) or {}
    execution = snapshot.get("execution", {}) or {}
    items: list[str] = []
    if status == "block":
        items.append("先处理阻断中的退出任务或漏执行问题，再考虑新增风险。")
    if int(lots.get("stale_open_lots", 0) or 0):
        items.append("先复核陈旧持仓批次；要么补上时限止损，要么重建持仓逻辑。")
    if int(exit_plan.get("sell_all_count", 0) or 0):
        items.append("先完成清仓任务，再考虑新的买入计划。")
    if int(lifecycle_rules.get("blocked_add_count", 0) or 0):
        items.append("Lifecycle rules are blocking adds; do not pyramid until the position proves strength and discipline is clean.")
    if int(lifecycle_rules.get("reduce_count", 0) or 0):
        items.append("Lifecycle rules require risk reduction before any new BUY.")
    if float(execution.get("lot_exit_execution_rate", 1) or 0) < 1 and int(execution.get("lot_exit_actionable_count", 0) or 0):
        items.append("分批退出执行不完整；确认目标批次是否真的已经平掉。")
    if float(execution.get("trade_plan_match_rate", 1) or 0) < 0.7 and int(execution.get("trade_plan_total", 0) or 0):
        items.append("计划命中率偏弱；在计划一致性恢复前，减少主观临盘单。")
    if not items:
        items.append("生命周期链路基本干净，可以按下一轮 pretrade 计划推进。")
    return items


def _trade_plan_snapshot(summary: dict | None) -> dict[str, Any]:
    summary = summary or {}
    return {
        "records": int(summary.get("total", 0) or 0),
        "planned_value": float(summary.get("planned_value", 0) or 0),
        "allowed_value": float(summary.get("allowed_value", 0) or 0),
        "block_count": int(summary.get("block_count", 0) or 0),
        "warn_count": int(summary.get("warn_count", 0) or 0),
    }


def _lot_snapshot(lot_book: dict | None) -> dict[str, Any]:
    lot_book = lot_book or {}
    summary = lot_book.get("summary", {}) or {}
    return {
        "open_lots": int(lot_book.get("total_open_lots", 0) or 0),
        "closed_lots": int(lot_book.get("total_closed_lots", 0) or 0),
        "stale_open_lots": int(summary.get("stale_open_lot_count", 0) or 0),
        "open_unrealized_pnl": float(lot_book.get("open_unrealized_pnl", 0) or 0),
        "realized_pnl": float(lot_book.get("realized_pnl", 0) or 0),
    }


def _holding_action_snapshot(plan: dict | None) -> dict[str, Any]:
    plan = plan or {}
    return {
        "status": str(plan.get("status", "pass") or "pass"),
        "exit_count": int(plan.get("exit_count", 0) or 0),
        "reduce_count": int(plan.get("reduce_count", 0) or 0),
        "watch_count": int(plan.get("watch_count", 0) or 0),
    }


def _exit_plan_snapshot(plan: dict | None) -> dict[str, Any]:
    plan = plan or {}
    return {
        "status": str(plan.get("status", "pass") or "pass"),
        "sell_all_count": int(plan.get("sell_all_count", 0) or 0),
        "take_profit_count": int(plan.get("take_profit_count", 0) or 0),
        "reduce_count": int(plan.get("reduce_count", 0) or 0),
        "time_stop_count": int(plan.get("time_stop_count", 0) or 0),
    }


def _lifecycle_rule_snapshot(plan: dict | None) -> dict[str, Any]:
    plan = plan or {}
    return {
        "status": str(plan.get("status", "pass") or "pass"),
        "add_count": int(plan.get("add_count", 0) or 0),
        "reduce_count": int(plan.get("reduce_count", 0) or 0),
        "exit_count": int(plan.get("exit_count", 0) or 0),
        "blocked_add_count": int(plan.get("blocked_add_count", 0) or 0),
        "probe_count": int(plan.get("probe_count", 0) or 0),
        "build_count": int(plan.get("build_count", 0) or 0),
        "core_count": int(plan.get("core_count", 0) or 0),
        "action_items": list(plan.get("action_items", []) or []),
        "exception_penalty": dict(plan.get("exception_penalty") or {}),
        "items": list(plan.get("items", []) or []),
    }


def _execution_snapshot(
    *,
    trade_plan_audit: dict | None,
    action_execution_summary: dict | None,
    exit_execution_summary: dict | None,
    lot_exit_execution_summary: dict | None,
) -> dict[str, Any]:
    trade_plan_audit = trade_plan_audit or {}
    action_execution_summary = action_execution_summary or {}
    exit_execution_summary = exit_execution_summary or {}
    lot_exit_execution_summary = lot_exit_execution_summary or {}
    return {
        "trade_plan_total": int(trade_plan_audit.get("total_plans", 0) or 0),
        "trade_plan_match_rate": float(trade_plan_audit.get("match_rate", 0) or 0),
        "action_actionable_count": int(action_execution_summary.get("actionable_count", 0) or 0),
        "action_execution_rate": float(action_execution_summary.get("execution_rate", 0) or 0),
        "action_missed_count": int(action_execution_summary.get("missed_count", 0) or 0),
        "exit_actionable_count": int(exit_execution_summary.get("actionable_count", 0) or 0),
        "exit_execution_rate": float(exit_execution_summary.get("execution_rate", 0) or 0),
        "exit_missed_count": int(exit_execution_summary.get("missed_count", 0) or 0),
        "lot_exit_actionable_count": int(lot_exit_execution_summary.get("actionable_count", 0) or 0),
        "lot_exit_execution_rate": float(lot_exit_execution_summary.get("execution_rate", 0) or 0),
        "lot_exit_missed_count": int(lot_exit_execution_summary.get("missed_count", 0) or 0),
    }


def _rollup_status(
    *,
    trade_plan_summary: dict | None,
    lot_book: dict | None,
    holding_action_plan: dict | None,
    exit_plan: dict | None,
    lifecycle_rule_plan: dict | None,
    trade_plan_audit: dict | None,
    action_execution_summary: dict | None,
    exit_execution_summary: dict | None,
    lot_exit_execution_summary: dict | None,
) -> str:
    if str((holding_action_plan or {}).get("status", "pass") or "pass") == "block":
        return "block"
    if str((exit_plan or {}).get("status", "pass") or "pass") == "block":
        return "block"
    if str((lifecycle_rule_plan or {}).get("status", "pass") or "pass") == "block":
        return "block"
    if int((action_execution_summary or {}).get("missed_count", 0) or 0):
        return "block"
    if int((exit_execution_summary or {}).get("missed_count", 0) or 0):
        return "block"
    if int((lot_exit_execution_summary or {}).get("missed_count", 0) or 0):
        return "block"
    if int((lot_book or {}).get("summary", {}).get("stale_open_lot_count", 0) or 0):
        return "warn"
    if str((holding_action_plan or {}).get("status", "pass") or "pass") == "warn":
        return "warn"
    if str((exit_plan or {}).get("status", "pass") or "pass") == "warn":
        return "warn"
    if str((lifecycle_rule_plan or {}).get("status", "pass") or "pass") == "warn":
        return "warn"
    if int((trade_plan_summary or {}).get("warn_count", 0) or 0):
        return "warn"
    if float((trade_plan_audit or {}).get("match_rate", 1) or 0) < 0.7 and int((trade_plan_audit or {}).get("total_plans", 0) or 0):
        return "warn"
    return "pass"
