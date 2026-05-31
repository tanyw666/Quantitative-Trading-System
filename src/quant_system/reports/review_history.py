from __future__ import annotations

from collections import Counter
from typing import Any


def build_review_history(
    *,
    trade_plans: list[dict[str, Any]] | None = None,
    trades: list[dict[str, Any]] | None = None,
    action_plans: list[dict[str, Any]] | None = None,
    exit_plans: list[dict[str, Any]] | None = None,
    lifecycle_snapshots: list[dict[str, Any]] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    trade_plans = list(trade_plans or [])
    trades = list(trades or [])
    action_plans = list(action_plans or [])
    exit_plans = list(exit_plans or [])
    lifecycle_snapshots = list(lifecycle_snapshots or [])
    visible_limit = max(int(limit), 0)
    return {
        "counts": {
            "trade_plans": len(trade_plans),
            "trades": len(trades),
            "action_plans": len(action_plans),
            "exit_plans": len(exit_plans),
            "lifecycle_snapshots": len(lifecycle_snapshots),
        },
        "trade_plan": _trade_plan_summary(trade_plans),
        "actions": _action_summary(action_plans),
        "exits": _exit_summary(exit_plans),
        "lifecycle": _lifecycle_summary(lifecycle_snapshots),
        "latest_lifecycle": lifecycle_snapshots[-visible_limit:] if visible_limit else lifecycle_snapshots,
        "action_items": _action_items(trade_plans, trades, action_plans, exit_plans, lifecycle_snapshots),
    }


def render_review_history_markdown(summary: dict[str, Any] | None) -> str:
    summary = summary or {}
    counts = summary.get("counts", {}) or {}
    trade_plan = summary.get("trade_plan", {}) or {}
    actions = summary.get("actions", {}) or {}
    exits = summary.get("exits", {}) or {}
    lifecycle = summary.get("lifecycle", {}) or {}
    lines = [
        "# Review History",
        "",
        "## Coverage",
        "",
        f"- Trade plans: {int(counts.get('trade_plans', 0) or 0)}",
        f"- Trades: {int(counts.get('trades', 0) or 0)}",
        f"- Holding action plans: {int(counts.get('action_plans', 0) or 0)}",
        f"- Exit plans: {int(counts.get('exit_plans', 0) or 0)}",
        f"- Lifecycle snapshots: {int(counts.get('lifecycle_snapshots', 0) or 0)}",
        "",
        "## Plan Discipline",
        "",
        f"- Planned value: {float(trade_plan.get('planned_value', 0) or 0):.2f}",
        f"- Allowed value: {float(trade_plan.get('allowed_value', 0) or 0):.2f}",
        f"- Status counts: {_format_counts(trade_plan.get('status_counts'))}",
        f"- Gate counts: {_format_counts(trade_plan.get('gate_counts'))}",
        "",
        "## Action And Exit",
        "",
        f"- Action status counts: {_format_counts(actions.get('status_counts'))}",
        f"- Exit status counts: {_format_counts(exits.get('status_counts'))}",
        f"- Sell-all tasks: {int(exits.get('sell_all_count', 0) or 0)}",
        f"- Expected cash release: {float(exits.get('expected_cash_release', 0) or 0):.2f}",
        "",
        "## Lifecycle",
        "",
        f"- Status counts: {_format_counts(lifecycle.get('status_counts'))}",
        f"- Average trade-plan match: {float(lifecycle.get('avg_trade_plan_match_rate', 0) or 0):.1%}",
        f"- Average action execution: {float(lifecycle.get('avg_action_execution_rate', 0) or 0):.1%}",
        f"- Average exit execution: {float(lifecycle.get('avg_exit_execution_rate', 0) or 0):.1%}",
        f"- Average lot-exit execution: {float(lifecycle.get('avg_lot_exit_execution_rate', 0) or 0):.1%}",
    ]
    action_items = list(summary.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in action_items)
    return "\n".join(lines)


def _trade_plan_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status_counts": _counts(records, "status"),
        "gate_counts": _counts(records, "gate_status"),
        "strategy_counts": _counts(records, "strategy"),
        "planned_value": round(sum(_float(item.get("planned_value")) for item in records), 2),
        "allowed_value": round(sum(_float(item.get("allowed_value")) for item in records), 2),
        "latest_date": _latest(records, "trade_date"),
    }


def _action_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status_counts": _counts(records, "status"),
        "exit_count": sum(int(item.get("exit_count", 0) or 0) for item in records),
        "reduce_count": sum(int(item.get("reduce_count", 0) or 0) for item in records),
        "watch_count": sum(int(item.get("watch_count", 0) or 0) for item in records),
        "latest_date": _latest(records, "action_date"),
    }


def _exit_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status_counts": _counts(records, "status"),
        "sell_all_count": sum(int(item.get("sell_all_count", 0) or 0) for item in records),
        "take_profit_count": sum(int(item.get("take_profit_count", 0) or 0) for item in records),
        "expected_cash_release": round(sum(_float(item.get("expected_cash_release")) for item in records), 2),
        "latest_date": _latest(records, "plan_date"),
    }


def _lifecycle_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status_counts": _counts(records, "status"),
        "avg_trade_plan_match_rate": _avg_nested(records, "execution", "trade_plan_match_rate"),
        "avg_action_execution_rate": _avg_nested(records, "execution", "action_execution_rate"),
        "avg_exit_execution_rate": _avg_nested(records, "execution", "exit_execution_rate"),
        "avg_lot_exit_execution_rate": _avg_nested(records, "execution", "lot_exit_execution_rate"),
        "latest_date": _latest(records, "snapshot_date"),
    }


def _action_items(
    trade_plans: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    action_plans: list[dict[str, Any]],
    exit_plans: list[dict[str, Any]],
    lifecycle_snapshots: list[dict[str, Any]],
) -> list[str]:
    items: list[str] = []
    if trade_plans and not trades:
        items.append("Trade plans exist but no trades have been recorded; review whether planned signals were ignored.")
    if trades and not trade_plans:
        items.append("Trades exist without persisted trade plans; record plans before execution to improve auditability.")
    if exit_plans:
        latest_exit = exit_plans[-1]
        if int(latest_exit.get("sell_all_count", 0) or 0):
            items.append("Latest exit plan contains sell-all tasks; resolve exits before adding new risk.")
    if action_plans:
        latest_action = action_plans[-1]
        if str(latest_action.get("status", "") or "") in {"warn", "block"}:
            items.append("Latest holding action plan is not clean; check reductions, stop-losses, and missing prices.")
    if lifecycle_snapshots:
        latest_lifecycle = lifecycle_snapshots[-1]
        if str(latest_lifecycle.get("status", "") or "") == "block":
            items.append("Latest lifecycle snapshot is blocked; pause new positions until execution gaps are closed.")
    if not items:
        items.append("Review history is clean enough for the next planned pretrade checks.")
    return items


def _counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    values = Counter(str(item.get(key, "") or "").strip() for item in records)
    return {key: count for key, count in sorted(values.items()) if key}


def _latest(records: list[dict[str, Any]], key: str) -> str:
    values = [str(item.get(key, "") or "").strip() for item in records if str(item.get(key, "") or "").strip()]
    return max(values) if values else ""


def _avg_nested(records: list[dict[str, Any]], parent: str, key: str) -> float:
    values = []
    for item in records:
        container = item.get(parent, {}) or {}
        if isinstance(container, dict) and container.get(key) not in (None, ""):
            values.append(float(container.get(key) or 0))
    return sum(values) / len(values) if values else 0.0


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _format_counts(value: object) -> str:
    if not isinstance(value, dict) or not value:
        return "-"
    return ", ".join(f"{key}={count}" for key, count in value.items())
