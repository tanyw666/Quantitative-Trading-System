from __future__ import annotations

from typing import Any


def build_review_doctor_report(
    *,
    selections: list[dict[str, Any]] | None = None,
    trades: list[dict[str, Any]] | None = None,
    trade_plans: list[dict[str, Any]] | None = None,
    execution_confirmations: list[dict[str, Any]] | None = None,
    action_plans: list[dict[str, Any]] | None = None,
    exit_plans: list[dict[str, Any]] | None = None,
    lifecycle_snapshots: list[dict[str, Any]] | None = None,
    trading_day_states: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    selections = list(selections or [])
    trades = list(trades or [])
    trade_plans = list(trade_plans or [])
    execution_confirmations = list(execution_confirmations or [])
    action_plans = list(action_plans or [])
    exit_plans = list(exit_plans or [])
    lifecycle_snapshots = list(lifecycle_snapshots or [])
    trading_day_states = list(trading_day_states or [])

    counts = {
        "selections": len(selections),
        "trades": len(trades),
        "trade_plans": len(trade_plans),
        "execution_confirmations": len(execution_confirmations),
        "action_plans": len(action_plans),
        "exit_plans": len(exit_plans),
        "lifecycle_snapshots": len(lifecycle_snapshots),
        "trading_day_states": len(trading_day_states),
    }
    latest = {
        "selection_date": _latest(selections, "date"),
        "trade_date": _latest(trades, "date"),
        "trade_plan_date": _latest(trade_plans, "trade_date"),
        "execution_confirmation_date": _latest(execution_confirmations, "created_at")[:10],
        "action_date": _latest(action_plans, "action_date"),
        "exit_plan_date": _latest(exit_plans, "plan_date"),
        "lifecycle_date": _latest(lifecycle_snapshots, "snapshot_date"),
        "trading_day_state_date": _latest(trading_day_states, "date"),
    }
    issues: list[dict[str, str]] = []

    if not any(counts.values()):
            issues.append(_issue("empty_review_ledger", "fail", "复盘账本为空；请先导入或持久化复盘记录。"))
    else:
        if counts["trades"] and not counts["trade_plans"]:
            issues.append(_issue("missing_trade_plans", "warn", "已有交易记录，但没有找到持久化交易计划。"))
        if counts["trade_plans"] and not counts["trades"]:
            issues.append(_issue("unexecuted_trade_plans", "warn", "已有交易计划，但尚未记录实际成交。"))
        if _buy_trade_count(trades) and not counts["execution_confirmations"]:
            issues.append(_issue("missing_execution_confirmations", "warn", "已有 BUY 交易，但没有找到持久化执行确认。"))
        if counts["execution_confirmations"] and not counts["trades"]:
            issues.append(_issue("orphan_execution_confirmations", "warn", "已有执行确认，但尚未记录实际成交。"))
        if counts["trades"] and not counts["lifecycle_snapshots"]:
            issues.append(_issue("missing_lifecycle_snapshots", "warn", "已有交易记录，但没有持久化生命周期快照。"))
        if counts["trades"] and not counts["trading_day_states"]:
            issues.append(_issue("missing_trading_day_states", "warn", "已有交易记录，但没有持久化交易日状态。"))
        if counts["action_plans"] and not counts["trades"]:
            issues.append(_issue("orphan_action_plans", "warn", "已有持仓动作计划，但账本中没有交易记录。"))
        if counts["exit_plans"] and not counts["trades"]:
            issues.append(_issue("orphan_exit_plans", "warn", "已有退出计划，但账本中没有交易记录。"))

    latest_trade_date = latest["trade_date"]
    latest_lifecycle_date = latest["lifecycle_date"]
    if latest_trade_date and latest_lifecycle_date and latest_trade_date > latest_lifecycle_date:
        issues.append(_issue("stale_lifecycle_snapshot", "warn", "最新交易日晚于最新生命周期快照。"))
    latest_state_date = latest["trading_day_state_date"]
    if latest_trade_date and latest_state_date and latest_trade_date > latest_state_date:
        issues.append(_issue("stale_trading_day_state", "warn", "最新交易日晚于最新交易日状态记录。"))
    latest_action_date = latest["action_date"]
    if latest_trade_date and latest_action_date and latest_trade_date > latest_action_date:
        issues.append(_issue("stale_action_plan", "warn", "最新交易日晚于最新持仓动作计划。"))
    latest_exit_date = latest["exit_plan_date"]
    if latest_trade_date and latest_exit_date and latest_trade_date > latest_exit_date:
        issues.append(_issue("stale_exit_plan", "warn", "最新交易日晚于最新退出计划。"))

    latest_lifecycle_status = _latest_status(lifecycle_snapshots)
    latest_trading_day_status = _latest_status_by_date(trading_day_states, "date")
    if latest_lifecycle_status == "block":
        issues.append(_issue("latest_lifecycle_blocked", "warn", "最新生命周期快照处于阻断状态；补齐执行缺口后再增加风险。"))
    if latest_trading_day_status == "block":
        issues.append(_issue("latest_trading_day_blocked", "warn", "最新交易日状态处于阻断状态；补齐阶段缺口后再开新风险。"))

    if exit_plans:
        latest_exit_plan = exit_plans[-1]
        if int(latest_exit_plan.get("sell_all_count", 0) or 0) > 0:
            issues.append(_issue("latest_exit_sell_all", "warn", "最新退出计划仍包含清仓任务。"))

    status = _rollup_status(issues)
    return {
        "status": status,
        "counts": counts,
        "latest": latest,
        "latest_lifecycle_status": latest_lifecycle_status,
        "latest_trading_day_status": latest_trading_day_status,
        "issues": issues,
        "action_items": _action_items(status, issues),
    }


def render_review_doctor_markdown(report: dict[str, Any] | None) -> str:
    report = report or {}
    counts = report.get("counts", {}) or {}
    latest = report.get("latest", {}) or {}
    issues = list(report.get("issues", []) or [])
    lines = [
        "# 复盘医生",
        "",
        f"- 状态：{report.get('status', 'pass')}",
        f"- 选股/交易/计划：{int(counts.get('selections', 0) or 0)} / {int(counts.get('trades', 0) or 0)} / {int(counts.get('trade_plans', 0) or 0)}",
        f"- 执行确认：{int(counts.get('execution_confirmations', 0) or 0)}",
        f"- 动作/退出/生命周期：{int(counts.get('action_plans', 0) or 0)} / {int(counts.get('exit_plans', 0) or 0)} / {int(counts.get('lifecycle_snapshots', 0) or 0)}",
        f"- 交易日状态：{int(counts.get('trading_day_states', 0) or 0)}",
        "",
        "## 最新记录",
        "",
        f"- 选股日期：{latest.get('selection_date', '') or '-'}",
        f"- 交易日期：{latest.get('trade_date', '') or '-'}",
        f"- 计划日期：{latest.get('trade_plan_date', '') or '-'}",
        f"- 执行确认日期：{latest.get('execution_confirmation_date', '') or '-'}",
        f"- 动作日期：{latest.get('action_date', '') or '-'}",
        f"- 退出计划日期：{latest.get('exit_plan_date', '') or '-'}",
        f"- 生命周期日期：{latest.get('lifecycle_date', '') or '-'}",
        f"- 交易日状态日期：{latest.get('trading_day_state_date', '') or '-'}",
        f"- 最新生命周期状态：{report.get('latest_lifecycle_status', '') or '-'}",
        f"- 最新交易日状态：{report.get('latest_trading_day_status', '') or '-'}",
        "",
        "## 问题",
        "",
    ]
    if issues:
        lines.extend(f"- [{item.get('status', '')}] {item.get('message', '')}" for item in issues)
    else:
        lines.append("- 暂未发现明显复盘账本问题。")
    action_items = list(report.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "## 行动项", ""])
        lines.extend(f"- {item}" for item in action_items)
    return "\n".join(lines)


def _latest(records: list[dict[str, Any]], key: str) -> str:
    values = [str(item.get(key, "") or "").strip() for item in records if str(item.get(key, "") or "").strip()]
    return max(values) if values else ""


def _buy_trade_count(records: list[dict[str, Any]]) -> int:
    return sum(1 for item in records if str(item.get("side", "") or "").upper() == "BUY")


def _latest_status(lifecycle_snapshots: list[dict[str, Any]]) -> str:
    if not lifecycle_snapshots:
        return ""
    latest = max(
        lifecycle_snapshots,
        key=lambda item: str(item.get("snapshot_date", "") or ""),
    )
    return str(latest.get("status", "") or "")


def _latest_status_by_date(records: list[dict[str, Any]], key: str) -> str:
    if not records:
        return ""
    latest = max(records, key=lambda item: str(item.get(key, "") or ""))
    return str(latest.get("status", "") or "")


def _issue(name: str, status: str, message: str) -> dict[str, str]:
    return {"name": name, "status": status, "message": message}


def _rollup_status(issues: list[dict[str, str]]) -> str:
    if any(str(item.get("status", "")) == "fail" for item in issues):
        return "fail"
    if issues:
        return "warn"
    return "pass"


def _action_items(status: str, issues: list[dict[str, str]]) -> list[str]:
    if status == "pass":
        return ["复盘账本完整度足够支撑下一交易日。"]
    items: list[str] = []
    names = {str(item.get("name", "")) for item in issues}
    if "missing_trade_plans" in names:
        items.append("执行前先持久化交易计划，便于盘后衡量计划一致性。")
    if "missing_execution_confirmations" in names or "orphan_execution_confirmations" in names:
        items.append("手动下单前先持久化执行确认，再把它绑定到 BUY 成交。")
    if "missing_lifecycle_snapshots" in names or "stale_lifecycle_snapshot" in names:
        items.append("重大交易或盘后复盘后，刷新并持久化生命周期快照。")
    if "missing_trading_day_states" in names or "stale_trading_day_state" in names:
        items.append("每日 workflow 后持久化交易日状态，便于复核阶段缺口。")
    if "latest_lifecycle_blocked" in names:
        items.append("最新生命周期快照处于阻断状态；清理阻断前暂停新开仓。")
    if "latest_trading_day_blocked" in names:
        items.append("最新交易日状态处于阻断状态；开新风险前先补齐阶段缺口。")
    if "latest_exit_sell_all" in names:
        items.append("先完成清仓退出任务，再打开额外风险。")
    if not items:
        items.append("复核上方预警项，补齐复盘账本中的断点。")
    return items
