from __future__ import annotations

from typing import Any


def build_trading_assistant(
    *,
    context: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
    timeline: dict[str, Any] | None = None,
    watchdog: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    context = context or {}
    cockpit = cockpit or {}
    timeline = timeline or {}
    watchdog = watchdog or {}
    state = state or {}
    battle_plan = dict(context.get("final_battle_plan") or cockpit.get("final_battle_plan") or {})
    approval_cooldown = dict(context.get("approval_cooldown") or cockpit.get("approval_cooldown") or {})
    status = _rollup_status(
        [
            str(battle_plan.get("status", "") or "pass"),
            str(cockpit.get("status", "") or "pass"),
            str(timeline.get("status", "") or "pass"),
            str(watchdog.get("status", "") or "pass"),
            str(state.get("status", "") or "pass"),
            str(approval_cooldown.get("status", "") or "pass"),
        ]
    )
    return {
        "status": status,
        "decision": _decision(status),
        "cards": {
            "market": _market_card(context, cockpit),
            "battle_plan": _battle_card(battle_plan),
            "approval_cooldown": _approval_card(approval_cooldown),
            "cockpit": _cockpit_card(cockpit),
            "timeline": _timeline_card(timeline, state),
            "watchdog": _watchdog_card(watchdog),
        },
        "urgent_actions": _urgent_actions(
            battle_plan=battle_plan,
            cockpit=cockpit,
            timeline=timeline,
            watchdog=watchdog,
            approval_cooldown=approval_cooldown,
            limit=limit,
        ),
        "buy_candidates": _buy_candidates(context, battle_plan, limit=limit),
        "blocked_candidates": list(battle_plan.get("blocked_candidates") or [])[: max(int(limit), 1)],
    }


def render_trading_assistant_markdown(report: dict[str, Any] | None) -> str:
    report = report or {}
    lines = [
        "# 交易助手",
        "",
        f"- 状态：{report.get('status', '')}",
        f"- 决策：{report.get('decision', '')}",
        "",
        "## 优先动作",
        "",
    ]
    actions = list(report.get("urgent_actions") or [])
    if actions:
        lines.extend(f"- [{item.get('priority', '')}] {item.get('text', '')}" for item in actions)
    else:
        lines.append("- 暂无紧急动作，继续按交易日清单执行。")

    cards = dict(report.get("cards") or {})
    for title, card in [
        ("市场与仓位", cards.get("market") or {}),
        ("最终作战单", cards.get("battle_plan") or {}),
        ("审批冷静期", cards.get("approval_cooldown") or {}),
        ("交易驾驶舱", cards.get("cockpit") or {}),
        ("交易日时间线", cards.get("timeline") or {}),
        ("交易日看板巡检", cards.get("watchdog") or {}),
    ]:
        lines.extend(["", f"## {title}", ""])
        if not card:
            lines.append("- 暂无数据。")
            continue
        for key, value in card.items():
            lines.append(f"- {_label(key)}: {value}")

    buys = list(report.get("buy_candidates") or [])
    lines.extend(["", "## 可执行候选", ""])
    if buys:
        for item in buys:
            lines.append(
                f"- [{item.get('status', '')}] {item.get('symbol', '')} {item.get('name', '')}: "
                f"计划={_pct(item.get('planned_pct'))}，允许={_pct(item.get('allowed_pct'))}，"
                f"入场={_price(item.get('entry_price'))}，止损={_price(item.get('stop_price'))}"
            )
    else:
        lines.append("- 当前最终作战单没有可执行候选。")

    blocked = list(report.get("blocked_candidates") or [])
    if blocked:
        lines.extend(["", "## 阻断候选", ""])
        for item in blocked:
            lines.append(f"- {item.get('symbol', '')} {item.get('name', '')}: {item.get('reason', '')}")
    return "\n".join(lines)


def _market_card(context: dict[str, Any], cockpit: dict[str, Any]) -> dict[str, Any]:
    market = dict(context.get("market_temperature") or {})
    allocation = dict(context.get("allocation_plan") or {})
    cockpit_market = dict(cockpit.get("market") or {})
    return {
        "regime": market.get("regime", cockpit_market.get("regime", "")),
        "stance": market.get("stance", cockpit_market.get("stance", "")),
        "target_exposure": _pct(allocation.get("target_exposure_pct")),
        "allocated": _pct(allocation.get("allocated_pct")),
        "strategy_action": allocation.get("strategy_action", ""),
        "strategy_alert": allocation.get("strategy_alert_level", ""),
    }


def _battle_card(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": plan.get("status", ""),
        "decision": plan.get("decision", ""),
        "must_do": len(list(plan.get("must_do") or [])),
        "buy_candidates": len(list(plan.get("buy_candidates") or [])),
        "blocked_candidates": len(list(plan.get("blocked_candidates") or [])),
    }


def _approval_card(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": summary.get("status", "pass"),
        "constraint_count": int(summary.get("constraint_count", 0) or 0),
        "block": int((summary.get("by_alert_level") or {}).get("block", 0) or 0),
        "warn": int((summary.get("by_alert_level") or {}).get("warn", 0) or 0),
    }


def _cockpit_card(cockpit: dict[str, Any]) -> dict[str, Any]:
    execution = dict(cockpit.get("execution_audit") or {})
    gate = dict(cockpit.get("gate_review") or {})
    position = dict(cockpit.get("position_control") or {})
    return {
        "status": cockpit.get("status", ""),
        "decision": cockpit.get("decision", ""),
        "execution_blocks": execution.get("block", 0),
        "execution_warns": execution.get("warn", 0),
        "gate_violations": gate.get("violations", 0),
        "lifecycle": position.get("lifecycle", ""),
    }


def _timeline_card(timeline: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    phases = list(timeline.get("phases") or [])
    phase_status = {
        str(item.get("phase", "")): str(item.get("status", ""))
        for item in phases
        if str(item.get("phase", ""))
    }
    return {
        "status": timeline.get("status", state.get("status", "")),
        "state_date": state.get("date", ""),
        "phase_count": len(phases) or state.get("phase_count", 0),
        "phase_status": phase_status,
        "action_items": len(list(timeline.get("action_items") or state.get("action_items") or [])),
    }


def _watchdog_card(watchdog: dict[str, Any]) -> dict[str, Any]:
    alerts = list(watchdog.get("alerts") or [])
    return {
        "status": watchdog.get("status", ""),
        "as_of": watchdog.get("as_of", ""),
        "latest_date": watchdog.get("latest_date", ""),
        "today_records": watchdog.get("today_record_count", 0),
        "alerts": len(alerts),
        "phase_issue_counts": watchdog.get("phase_issue_counts", {}),
    }


def _urgent_actions(
    *,
    battle_plan: dict[str, Any],
    cockpit: dict[str, Any],
    timeline: dict[str, Any],
    watchdog: dict[str, Any],
    approval_cooldown: dict[str, Any],
    limit: int,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in list(battle_plan.get("must_do") or []):
        items.append({"priority": str(item.get("priority", "P0") or "P0"), "text": str(item.get("text", "") or "")})
    for item in list(cockpit.get("action_items") or []):
        items.append({"priority": str(item.get("priority", "P1") or "P1"), "text": str(item.get("text", "") or "")})
    for text in list(timeline.get("action_items") or []):
        items.append({"priority": "P1", "text": str(text)})
    for text in list(approval_cooldown.get("action_items") or []):
        items.append({"priority": "P0" if approval_cooldown.get("status") == "block" else "P1", "text": str(text)})
    for text in list(watchdog.get("action_items") or []):
        items.append({"priority": "P0" if watchdog.get("status") == "block" else "P1", "text": str(text)})
    return _dedupe_items(items)[: max(int(limit), 1)]


def _buy_candidates(context: dict[str, Any], battle_plan: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    candidates = list(battle_plan.get("buy_candidates") or [])
    if candidates:
        return candidates[: max(int(limit), 1)]
    pretrade = [
        {
            "symbol": item.get("symbol", ""),
            "name": (item.get("candidate_snapshot") or {}).get("name", ""),
            "status": item.get("status", ""),
            "planned_pct": item.get("planned_pct"),
            "allowed_pct": item.get("allowed_pct"),
            "entry_price": item.get("entry_price"),
            "stop_price": item.get("stop_price"),
        }
        for item in list(context.get("pretrade_checks") or [])
        if str(item.get("status", "")) != "block"
    ]
    return pretrade[: max(int(limit), 1)]


def _dedupe_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in sorted(items, key=lambda row: row.get("priority", "P9")):
        text = str(item.get("text", "") or "")
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(item)
    return result


def _rollup_status(statuses: list[str]) -> str:
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _decision(status: str) -> str:
    if status == "block":
        return "禁止新增买入。先清理阻断、回写成交，并刷新工作流。"
    if status == "warn":
        return "只允许降仓确认单。增加风险前先处理预警。"
    return "允许按计划执行，但每一笔真实订单仍需先做组合确认。"


def _pct(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.1%}"


def _price(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.2f}"


def _label(key: str) -> str:
    labels = {
        "regime": "市场状态",
        "stance": "策略姿态",
        "target_exposure": "目标仓位",
        "allocated": "已分配仓位",
        "strategy_action": "策略动作",
        "strategy_alert": "策略预警",
        "status": "状态",
        "decision": "决策",
        "must_do": "必做事项",
        "buy_candidates": "可买候选",
        "blocked_candidates": "阻断候选",
        "constraint_count": "约束数量",
        "block": "阻断",
        "warn": "预警",
        "execution_blocks": "执行阻断",
        "execution_warns": "执行预警",
        "gate_violations": "门禁违规",
        "lifecycle": "生命周期",
        "state_date": "状态日期",
        "phase_count": "阶段数",
        "phase_status": "阶段状态",
        "action_items": "待办数",
        "as_of": "检查日期",
        "latest_date": "最近日期",
        "today_records": "当日记录",
        "alerts": "告警数",
        "phase_issue_counts": "阶段问题",
    }
    return labels.get(key, key)
