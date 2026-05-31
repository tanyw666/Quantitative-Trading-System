from __future__ import annotations

from typing import Any


def build_final_battle_plan(context: dict[str, Any] | None, *, limit: int = 5) -> dict[str, Any]:
    context = context or {}
    market = dict(context.get("market_temperature") or {})
    allocation = dict(context.get("allocation_plan") or {})
    holding_risk = dict(context.get("holding_risk") or {})
    holding_action = dict(context.get("holding_action_plan") or {})
    exit_plan = dict(context.get("exit_plan") or {})
    lifecycle = dict(context.get("lifecycle_snapshot") or {})
    lifecycle_rule_plan = dict(context.get("lifecycle_rule_plan") or {})
    strategy_health = list(context.get("strategy_health") or [])
    pretrade_checks = list(context.get("pretrade_checks") or [])

    leader = strategy_health[0] if strategy_health else {}
    lifecycle_pressure = dict((leader or {}).get("lifecycle_pressure") or {})
    gate = _rollup_gate(
        market=market,
        allocation=allocation,
        holding_risk=holding_risk,
        holding_action=holding_action,
        exit_plan=exit_plan,
        lifecycle_rule_plan=lifecycle_rule_plan,
        pretrade_checks=pretrade_checks,
        lifecycle_pressure=lifecycle_pressure,
    )
    must_do = _must_do_items(holding_action, exit_plan, lifecycle_rule_plan, lifecycle_pressure, pretrade_checks)
    buy_candidates = _buy_candidates(pretrade_checks, allocation, gate=gate, limit=limit)
    return {
        "status": gate["status"],
        "decision": gate["decision"],
        "reasons": gate["reasons"],
        "market_regime": market.get("regime", ""),
        "market_stance": market.get("stance", ""),
        "target_exposure_pct": _float(allocation.get("target_exposure_pct")),
        "allocated_pct": _float(allocation.get("allocated_pct")),
        "strategy_action": allocation.get("strategy_action", ""),
        "strategy_alert_level": allocation.get("strategy_alert_level", "pass"),
        "strategy_adjustment_note": allocation.get("strategy_adjustment_note", ""),
        "review_memory": lifecycle_pressure,
        "lifecycle_status": lifecycle.get("status", ""),
        "lifecycle_rule_status": lifecycle_rule_plan.get("status", ""),
        "must_do": must_do[: max(limit, 1)],
        "buy_candidates": buy_candidates["allowed"],
        "blocked_candidates": buy_candidates["blocked"],
        "pretrade_counts": _status_counts(pretrade_checks),
        "holding_action_counts": {
            "exit": int(holding_action.get("exit_count", 0) or 0),
            "reduce": int(holding_action.get("reduce_count", 0) or 0),
            "watch": int(holding_action.get("watch_count", 0) or 0),
        },
        "exit_plan_counts": {
            "sell_all": int(exit_plan.get("sell_all_count", 0) or 0),
            "take_profit": int(exit_plan.get("take_profit_count", 0) or 0),
            "reduce": int(exit_plan.get("reduce_count", 0) or 0),
            "time_stop": int(exit_plan.get("time_stop_count", 0) or 0),
        },
    }


def render_final_battle_plan_markdown(plan: dict[str, Any] | None) -> str:
    return "\n".join(render_final_battle_plan_lines(plan))


def render_final_battle_plan_lines(plan: dict[str, Any] | None) -> list[str]:
    plan = plan or {}
    if not plan:
        return ["- 暂无最终作战单。"]
    lines = [
        f"- 最终门禁：{plan.get('status', 'pass')}",
        f"- 执行结论：{plan.get('decision', '')}",
        f"- 市场：{plan.get('market_regime', '')} / {plan.get('market_stance', '')}",
        f"- 仓位：目标 {_pct(plan.get('target_exposure_pct'))}，已分配 {_pct(plan.get('allocated_pct'))}",
    ]
    if plan.get("strategy_adjustment_note"):
        lines.append(f"- 策略/仓位约束：{plan.get('strategy_adjustment_note')}")
    memory = dict(plan.get("review_memory") or {})
    if memory:
        lines.append(f"- Review memory：{memory.get('summary', '')}")
        if memory.get("doctor_status"):
            lines.append(f"- Review doctor：{memory.get('doctor_status')} / {int(memory.get('doctor_issue_count', 0) or 0)} issues")
    reasons = list(plan.get("reasons") or [])
    if reasons:
        lines.extend(["", "### 门禁原因", ""])
        lines.extend(f"- {item}" for item in reasons)
    must_do = list(plan.get("must_do") or [])
    lines.extend(["", "### 先处理", ""])
    if must_do:
        lines.extend(f"- [{item.get('priority', '')}] {item.get('text', '')}" for item in must_do)
    else:
        lines.append("- 无必须先处理的持仓/清仓任务。")
    buys = list(plan.get("buy_candidates") or [])
    lines.extend(["", "### 可执行候选", ""])
    if buys:
        for item in buys:
            lines.append(
                f"- [{item.get('status', '')}] {item.get('symbol', '')} {item.get('name', '')}: "
                f"计划 {_pct(item.get('planned_pct'))}, 上限 {_pct(item.get('allowed_pct'))}, "
                f"买入 {float(item.get('entry_price', 0) or 0):.2f}, "
                f"止损 {_price(item.get('stop_price'))}, 目标 {_price(item.get('target_price'))}"
            )
            for summary in list(item.get("pretrade_summary") or []):
                lines.append(f"  - {summary}")
    else:
        lines.append("- 当前没有通过最终门禁的新增买入。")
    blocked = list(plan.get("blocked_candidates") or [])
    if blocked:
        lines.extend(["", "### 禁止新增", ""])
        for item in blocked:
            lines.append(f"- {item.get('symbol', '')} {item.get('name', '')}: {item.get('reason', '')}")
            for summary in list(item.get("pretrade_summary") or []):
                lines.append(f"  - {summary}")
    return lines


def _rollup_gate(
    *,
    market: dict[str, Any],
    allocation: dict[str, Any],
    holding_risk: dict[str, Any],
    holding_action: dict[str, Any],
    exit_plan: dict[str, Any],
    lifecycle_rule_plan: dict[str, Any],
    pretrade_checks: list[dict[str, Any]],
    lifecycle_pressure: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    status = "pass"
    pretrade_statuses = [str(item.get("status", "") or "") for item in pretrade_checks]
    strategy_action = str(allocation.get("strategy_action", "") or "")
    strategy_alert = str(allocation.get("strategy_alert_level", "pass") or "pass")
    lifecycle_level = str(lifecycle_pressure.get("alert_level", "pass") or "pass")
    lifecycle_action = str(lifecycle_pressure.get("action", "keep") or "keep")
    regime = str(market.get("regime", "") or "")

    block_checks = [
        (regime in {"frozen", "empty"}, f"market regime is {regime}"),
        (str(holding_risk.get("status", "pass")) == "block", "holding risk is blocked"),
        (str(holding_action.get("status", "pass")) == "block", "holding action plan is blocked"),
        (str(exit_plan.get("status", "pass")) == "block", "exit plan is blocked"),
        (str(lifecycle_rule_plan.get("status", "pass")) == "block", "position lifecycle rules block new adds"),
        ("block" in pretrade_statuses, "at least one pretrade check is blocked"),
        (strategy_action == "pause" or strategy_alert == "block", "strategy gate blocks new positions"),
        (lifecycle_action == "pause" or lifecycle_level == "block", "review memory blocks new risk"),
    ]
    for blocked, reason in block_checks:
        if blocked:
            status = "block"
            reasons.append(reason)

    if status != "block":
        warn_checks = [
            (regime == "cold", "market regime is cold"),
            (str(holding_risk.get("status", "pass")) == "warn", "holding risk has warnings"),
            (str(holding_action.get("status", "pass")) == "warn", "holding action plan has warnings"),
            (str(exit_plan.get("status", "pass")) == "warn", "exit plan has warnings"),
            (str(lifecycle_rule_plan.get("status", "pass")) == "warn", "position lifecycle rules require reduced risk"),
            ("warn" in pretrade_statuses, "at least one pretrade check has warnings"),
            (strategy_action == "reduce" or strategy_alert == "warn", "strategy gate requires reduced size"),
            (lifecycle_action == "reduce" or lifecycle_level == "warn", "review memory requires reduced risk"),
        ]
        for warned, reason in warn_checks:
            if warned:
                status = "warn"
                reasons.append(reason)

    decision = {
        "pass": "允许按作战单执行，但正式买入前仍需用实时价格重跑单票 precheck。",
        "warn": "只允许计划内确认单；先处理预警项，禁止追高和临时加仓。",
        "block": "禁止新增买入；先处理阻断项、清仓/减仓任务和复盘账本缺口。",
    }[status]
    return {"status": status, "decision": decision, "reasons": reasons}


def _must_do_items(
    holding_action: dict[str, Any],
    exit_plan: dict[str, Any],
    lifecycle_rule_plan: dict[str, Any],
    lifecycle_pressure: dict[str, Any],
    pretrade_checks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for action in list(holding_action.get("actions", []) or []):
        action_name = str(action.get("action", "") or "")
        if action_name in {"exit", "reduce", "watch"}:
            items.append(
                {
                    "priority": "P0" if action_name == "exit" else "P1",
                    "text": f"{action.get('symbol', '')} {action_name}: {action.get('reason', '')}",
                }
            )
    for item in list(exit_plan.get("items", []) or []):
        action = str(item.get("action", "") or "")
        if action in {"sell_all", "reduce", "take_profit"}:
            items.append(
                {
                    "priority": "P0" if action == "sell_all" else "P1",
                    "text": f"{item.get('symbol', '')} {action}: {item.get('reason', item.get('plan_type', ''))}",
                }
            )
    for text in list(lifecycle_rule_plan.get("action_items", []) or []):
        items.append(
            {
                "priority": "P0" if str(lifecycle_rule_plan.get("status", "pass") or "pass") == "block" else "P1",
                "text": str(text),
            }
        )
    if lifecycle_pressure and str(lifecycle_pressure.get("alert_level", "")) in {"warn", "block"}:
        items.append({"priority": "P0", "text": f"Review memory: {lifecycle_pressure.get('summary', '')}"})
    for check in pretrade_checks:
        if str(check.get("status", "")) == "block":
            symbol = str(check.get("symbol", "") or "")
            items.append({"priority": "P0", "text": f"{symbol} pretrade blocked; do not place new buy order."})
    return items


def _buy_candidates(
    pretrade_checks: list[dict[str, Any]],
    allocation: dict[str, Any],
    *,
    gate: dict[str, Any],
    limit: int,
) -> dict[str, list[dict[str, Any]]]:
    allocation_by_symbol = {
        str(item.get("symbol", "")).zfill(6): item
        for item in list(allocation.get("items", []) or [])
    }
    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for check in pretrade_checks:
        status = str(check.get("status", "") or "")
        symbol = str(check.get("symbol", "") or "").zfill(6)
        candidate = dict(check.get("candidate_snapshot") or {})
        row = {
            "symbol": symbol,
            "name": candidate.get("name", ""),
            "status": status,
            "planned_pct": _float(check.get("planned_pct")),
            "allowed_pct": _float(check.get("allowed_pct")),
            "planned_value": _float(check.get("planned_value")),
            "allowed_value": _float(check.get("allowed_value")),
            "entry_price": _float(check.get("entry_price")),
            "stop_price": check.get("stop_price"),
            "target_price": check.get("target_price"),
            "reward_risk": check.get("reward_risk"),
            "reason": str(candidate.get("reason", "") or ""),
            "pretrade_summary": _candidate_trade_summary(check),
            "allocation": allocation_by_symbol.get(symbol, {}),
        }
        if str(gate.get("status", "")) == "block":
            row["reason"] = "final gate blocked: " + "; ".join(list(gate.get("reasons") or [])[:3])
            blocked.append(row)
        elif status == "block":
            row["reason"] = _focus_reason(check)
            blocked.append(row)
        else:
            allowed.append(row)
    return {"allowed": allowed[: max(limit, 1)], "blocked": blocked[: max(limit, 1)]}


def _focus_reason(check: dict[str, Any]) -> str:
    for item in list(check.get("checks", []) or []):
        if str(item.get("status", "")) == "block":
            return str(item.get("message", "") or "blocked")
    return "blocked"


def _candidate_trade_summary(check: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for item in list(check.get("checks", []) or []):
        status = str(item.get("status", "") or "")
        if status in {"warn", "block"}:
            messages.append(f"[{status}] {item.get('message', '')}")
    return messages[:3]


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pass": 0, "warn": 0, "block": 0}
    for item in records:
        status = str(item.get("status", "") or "")
        if status in counts:
            counts[status] += 1
    return counts


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _pct(value: Any) -> str:
    return f"{_float(value):.1%}"


def _price(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.2f}"
