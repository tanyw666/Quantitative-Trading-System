from __future__ import annotations

from typing import Any


def build_trading_cockpit(
    context: dict[str, Any] | None,
    *,
    execution_audit: dict[str, Any] | None = None,
    trade_plan_audit: dict[str, Any] | None = None,
    gate_review: dict[str, Any] | None = None,
    execution_confirmations: list[dict[str, Any]] | None = None,
    approval_cooldown: dict[str, Any] | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    context = context or {}
    final_plan = dict(context.get("final_battle_plan") or {})
    holding_risk = dict(context.get("holding_risk") or {})
    holding_action = dict(context.get("holding_action_plan") or {})
    exit_plan = dict(context.get("exit_plan") or {})
    lifecycle = dict(context.get("lifecycle_snapshot") or {})
    lifecycle_rule = dict(context.get("lifecycle_rule_plan") or {})
    execution_audit = execution_audit or {}
    trade_plan_audit = trade_plan_audit or {}
    gate_review = gate_review or context.get("gate_review") or {}
    approval_cooldown = approval_cooldown or context.get("approval_cooldown") or {}
    confirmations = list(execution_confirmations or [])
    gate = _rollup_cockpit_gate(
        final_plan=final_plan,
        holding_risk=holding_risk,
        holding_action=holding_action,
        exit_plan=exit_plan,
        lifecycle=lifecycle,
        lifecycle_rule=lifecycle_rule,
        execution_audit=execution_audit,
        trade_plan_audit=trade_plan_audit,
        gate_review=gate_review,
        approval_cooldown=approval_cooldown,
    )
    return {
        "status": gate["status"],
        "decision": gate["decision"],
        "reasons": gate["reasons"],
        "market": _market_card(context),
        "final_battle_plan": _final_plan_card(final_plan),
        "approval_cooldown": _approval_cooldown_card(approval_cooldown),
        "execution_audit": _execution_audit_card(execution_audit),
        "trade_plan_audit": _trade_plan_card(trade_plan_audit),
        "gate_review": _gate_review_card(gate_review),
        "position_control": _position_card(holding_risk, holding_action, exit_plan, lifecycle, lifecycle_rule),
        "confirmations": _confirmation_card(confirmations),
        "candidates": _candidate_card(context, limit=limit),
        "action_items": _action_items(
            final_plan=final_plan,
            holding_action=holding_action,
            exit_plan=exit_plan,
            lifecycle=lifecycle,
            lifecycle_rule=lifecycle_rule,
            execution_audit=execution_audit,
            trade_plan_audit=trade_plan_audit,
            gate_review=gate_review,
            approval_cooldown=approval_cooldown,
            execution_confirmations=confirmations,
            limit=limit,
        ),
    }


def render_trading_cockpit_markdown(cockpit: dict[str, Any] | None) -> str:
    cockpit = cockpit or {}
    if not cockpit:
        return "# 交易驾驶舱\n\n- 暂无驾驶舱数据。\n"
    lines = [
        "# 交易驾驶舱",
        "",
        f"- 状态：{cockpit.get('status', '')}",
        f"- 决策：{cockpit.get('decision', '')}",
    ]
    reasons = list(cockpit.get("reasons") or [])
    if reasons:
        lines.extend(["", "## 阻断与预警原因", ""])
        lines.extend(f"- {item}" for item in reasons)
    lines.extend(["", "## 优先动作", ""])
    action_items = list(cockpit.get("action_items") or [])
    if action_items:
        lines.extend(f"- [{item.get('priority', '')}] {item.get('text', '')}" for item in action_items)
    else:
        lines.append("- 暂无强制动作，继续按交易日工作流执行。")

    _extend_card(lines, "市场与仓位", cockpit.get("market") or {})
    _extend_card(lines, "最终作战单", cockpit.get("final_battle_plan") or {})
    _extend_card(lines, "审批冷静期", cockpit.get("approval_cooldown") or {})
    _extend_card(lines, "执行审计", cockpit.get("execution_audit") or {})
    _extend_card(lines, "交易计划审计", cockpit.get("trade_plan_audit") or {})
    _extend_card(lines, "门禁纪律", cockpit.get("gate_review") or {})
    _extend_card(lines, "持仓与退出控制", cockpit.get("position_control") or {})
    _extend_card(lines, "执行确认", cockpit.get("confirmations") or {})

    candidates = list((cockpit.get("candidates") or {}).get("records", []) or [])
    lines.extend(["", "## 可执行候选", ""])
    if candidates:
        lines.extend(
            f"- [{item.get('status', '')}] {item.get('symbol', '')} {item.get('name', '')}: "
            f"计划仓位 {_pct(item.get('planned_pct'))}，允许仓位 {_pct(item.get('allowed_pct'))}"
            for item in candidates
        )
    else:
        lines.append("- 暂无可展示的可执行候选。")
    return "\n".join(lines)


def _extend_card(lines: list[str], title: str, card: dict[str, Any]) -> None:
    lines.extend(["", f"## {title}", ""])
    if not card:
        lines.append("- 暂无数据。")
        return
    for key, value in card.items():
        if key == "records":
            continue
        lines.append(f"- {_label(key)}: {value}")


def _rollup_cockpit_gate(
    *,
    final_plan: dict[str, Any],
    holding_risk: dict[str, Any],
    holding_action: dict[str, Any],
    exit_plan: dict[str, Any],
    lifecycle: dict[str, Any],
    lifecycle_rule: dict[str, Any],
    execution_audit: dict[str, Any],
    trade_plan_audit: dict[str, Any],
    gate_review: dict[str, Any],
    approval_cooldown: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    status = "pass"
    block_checks = [
        (final_plan.get("status") == "block", "最终作战单阻断新增 BUY。"),
        (holding_risk.get("status") == "block", "持仓风险阻断执行。"),
        (holding_action.get("status") == "block", "持仓动作计划阻断执行。"),
        (exit_plan.get("status") == "block", "退出计划存在阻断级卖出任务。"),
        (lifecycle.get("status") == "block", "持仓生命周期闭环处于阻断。"),
        (int(execution_audit.get("block_count", 0) or 0) > 0, "执行确认审计存在阻断级偏差。"),
        (str(approval_cooldown.get("status", "") or "") == "block", "审批冷静期阻断相关策略。"),
        (
            int(gate_review.get("violation_count", 0) or 0) > 0
            and int(gate_review.get("buy_status_counts", {}).get("block", 0) or 0) > 0,
            "存在阻断门禁下记录的 BUY。",
        ),
    ]
    for blocked, reason in block_checks:
        if blocked:
            status = "block"
            reasons.append(reason)
    if lifecycle_rule.get("status") == "block":
        status = "block"
        reasons.append("Lifecycle rules block adds or require risk cleanup.")

    if status != "block":
        if lifecycle_rule.get("status") == "warn":
            status = "warn"
            reasons.append("Lifecycle rules require slower adds or a reduction first.")
        warn_checks = [
            (final_plan.get("status") == "warn", "最终作战单要求降仓执行。"),
            (holding_risk.get("status") == "warn", "持仓风险存在预警。"),
            (holding_action.get("status") == "warn", "持仓动作计划存在预警。"),
            (exit_plan.get("status") == "warn", "退出计划存在预警任务。"),
            (lifecycle.get("status") == "warn", "持仓生命周期闭环存在预警。"),
            (int(execution_audit.get("warn_count", 0) or 0) > 0, "执行确认审计存在预警。"),
            (int(execution_audit.get("missing_confirmation_trade_count", 0) or 0) > 0, "BUY 交易缺少执行确认。"),
            (str(approval_cooldown.get("status", "") or "") == "warn", "审批冷静期要求降低暴露。"),
            (
                float(trade_plan_audit.get("match_rate", 1.0) or 0) < 0.85
                and int(trade_plan_audit.get("total_plans", 0) or 0) > 0,
                "交易计划命中率偏低。",
            ),
            (int(gate_review.get("violation_count", 0) or 0) > 0, "存在预警/阻断门禁下记录的 BUY。"),
        ]
        for warned, reason in warn_checks:
            if warned:
                status = "warn"
                reasons.append(reason)

    decision = {
        "pass": "单票完成组合确认后，才允许按计划执行。",
        "warn": "只允许降仓确认单；增加风险前先清理预警。",
        "block": "禁止新增 BUY；先清理阻断、回写成交，并刷新审批纪律。",
    }[status]
    return {"status": status, "decision": decision, "reasons": reasons}


def _market_card(context: dict[str, Any]) -> dict[str, Any]:
    market = dict(context.get("market_temperature") or {})
    allocation = dict(context.get("allocation_plan") or {})
    return {
        "regime": market.get("regime", ""),
        "stance": market.get("stance", ""),
        "target_exposure": _pct(allocation.get("target_exposure_pct")),
        "allocated": _pct(allocation.get("allocated_pct")),
        "strategy_action": allocation.get("strategy_action", ""),
        "strategy_alert": allocation.get("strategy_alert_level", ""),
    }


def _final_plan_card(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": plan.get("status", ""),
        "decision": plan.get("decision", ""),
        "must_do": len(list(plan.get("must_do") or [])),
        "buy_candidates": len(list(plan.get("buy_candidates") or [])),
        "blocked_candidates": len(list(plan.get("blocked_candidates") or [])),
    }


def _approval_cooldown_card(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": summary.get("status", "pass"),
        "constraint_count": int(summary.get("constraint_count", 0) or 0),
        "block": int((summary.get("by_alert_level") or {}).get("block", 0) or 0),
        "warn": int((summary.get("by_alert_level") or {}).get("warn", 0) or 0),
    }


def _execution_audit_card(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "confirms": int(summary.get("total_confirms", 0) or 0),
        "buy_trades": int(summary.get("total_buy_trades", 0) or 0),
        "matched": int(summary.get("matched_trade_count", 0) or 0),
        "missing_writeback": int(summary.get("missing_trade_writeback_count", 0) or 0),
        "missing_confirmation": int(summary.get("missing_confirmation_trade_count", 0) or 0),
        "warn": int(summary.get("warn_count", 0) or 0),
        "block": int(summary.get("block_count", 0) or 0),
        "avg_price_gap": _pct(summary.get("avg_trade_vs_confirm_price_gap_pct")),
    }


def _trade_plan_card(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "plans": int(summary.get("total_plans", 0) or 0),
        "matched": int(summary.get("matched_trades", 0) or 0),
        "unmatched": int(summary.get("unmatched_plans", 0) or 0),
        "orphan": int(summary.get("orphan_trades", 0) or 0),
        "match_rate": _pct(summary.get("match_rate")),
        "avg_price_deviation": _pct(summary.get("avg_price_deviation_pct")),
    }


def _gate_review_card(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "gate_records": int(summary.get("gate_record_count", 0) or 0),
        "missing_gate": int(summary.get("missing_gate_count", 0) or 0),
        "violations": int(summary.get("violation_count", 0) or 0),
        "violation_rate": _pct(summary.get("violation_rate")),
    }


def _position_card(
    holding_risk: dict[str, Any],
    holding_action: dict[str, Any],
    exit_plan: dict[str, Any],
    lifecycle: dict[str, Any],
    lifecycle_rule: dict[str, Any],
) -> dict[str, Any]:
    return {
        "holding_risk": holding_risk.get("status", ""),
        "holding_exit": int(holding_action.get("exit_count", 0) or 0),
        "holding_reduce": int(holding_action.get("reduce_count", 0) or 0),
        "exit_sell_all": int(exit_plan.get("sell_all_count", 0) or 0),
        "exit_reduce": int(exit_plan.get("reduce_count", 0) or 0),
        "lifecycle": lifecycle.get("status", ""),
        "lifecycle_rules": lifecycle_rule.get("status", ""),
        "rule_add": int(lifecycle_rule.get("add_count", 0) or 0),
        "rule_reduce": int(lifecycle_rule.get("reduce_count", 0) or 0),
        "rule_blocked_add": int(lifecycle_rule.get("blocked_add_count", 0) or 0),
    }


def _confirmation_card(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for item in records:
        status = str(item.get("status", "") or "")
        if status:
            counts[status] = counts.get(status, 0) + 1
    return {
        "total": len(records),
        "pass": counts.get("pass", 0),
        "warn": counts.get("warn", 0),
        "block": counts.get("block", 0),
    }


def _candidate_card(context: dict[str, Any], *, limit: int) -> dict[str, Any]:
    final_plan = dict(context.get("final_battle_plan") or {})
    records = list(final_plan.get("buy_candidates") or [])
    if not records:
        records = [
            {
                "symbol": item.get("symbol", ""),
                "name": (item.get("candidate_snapshot") or {}).get("name", ""),
                "status": item.get("status", ""),
                "planned_pct": item.get("planned_pct"),
                "allowed_pct": item.get("allowed_pct"),
            }
            for item in list(context.get("pretrade_checks") or [])
            if str(item.get("status", "")) != "block"
        ]
    return {"records": records[: max(limit, 1)]}


def _action_items(
    *,
    final_plan: dict[str, Any],
    holding_action: dict[str, Any],
    exit_plan: dict[str, Any],
    lifecycle: dict[str, Any],
    lifecycle_rule: dict[str, Any],
    execution_audit: dict[str, Any],
    trade_plan_audit: dict[str, Any],
    gate_review: dict[str, Any],
    approval_cooldown: dict[str, Any],
    execution_confirmations: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in list(final_plan.get("must_do") or []):
        items.append({"priority": str(item.get("priority", "P0") or "P0"), "text": str(item.get("text", "") or "")})
    for action in list(holding_action.get("actions", []) or []):
        if str(action.get("action", "") or "") in {"exit", "reduce"}:
            priority = "P0" if action.get("action") == "exit" else "P1"
            items.append({"priority": priority, "text": f"{action.get('symbol', '')} {action.get('action', '')}: {action.get('reason', '')}"})
    for exit_item in list(exit_plan.get("items", []) or []):
        if str(exit_item.get("action", "") or "") in {"sell_all", "reduce", "take_profit"}:
            priority = "P0" if exit_item.get("action") == "sell_all" else "P1"
            items.append({"priority": priority, "text": f"{exit_item.get('symbol', '')} {exit_item.get('action', '')}: {exit_item.get('reason', exit_item.get('plan_type', ''))}"})
    for text in list(lifecycle_rule.get("action_items", []) or []):
        items.append({"priority": "P0" if lifecycle_rule.get("status") == "block" else "P1", "text": str(text)})
    for text in list(approval_cooldown.get("action_items", []) or []):
        items.append({"priority": "P0" if approval_cooldown.get("status") == "block" else "P1", "text": str(text)})
    for text in list(execution_audit.get("action_items", []) or []):
        items.append({"priority": "P0" if int(execution_audit.get("block_count", 0) or 0) else "P1", "text": str(text)})
    for text in list(trade_plan_audit.get("action_items", []) or []):
        items.append({"priority": "P1", "text": str(text)})
    for text in list(gate_review.get("action_items", []) or []):
        items.append({"priority": "P1", "text": str(text)})
    if lifecycle.get("status") == "block":
        items.append({"priority": "P0", "text": "持仓生命周期处于阻断；新增 BUY 风险前先闭合执行链路。"})
    if not execution_confirmations and list(final_plan.get("buy_candidates") or []):
        items.append({"priority": "P1", "text": "存在可执行候选；任何真实下单前必须先跑组合确认。"})
    if int(execution_audit.get("missing_trade_writeback_count", 0) or 0) > 0:
        items.append({"priority": "P0", "text": "执行确认缺少成交回写；继续前先记录成交或标记跳过订单。"})
    return _dedupe_items(items)[: max(limit, 1)]


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


def _pct(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.1%}"


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
        "confirms": "确认记录",
        "buy_trades": "买入交易",
        "matched": "已匹配",
        "missing_writeback": "缺成交回写",
        "missing_confirmation": "缺执行确认",
        "avg_price_gap": "平均价差",
        "plans": "计划数",
        "unmatched": "未匹配计划",
        "orphan": "孤立交易",
        "match_rate": "命中率",
        "avg_price_deviation": "平均价格偏差",
        "gate_records": "门禁记录",
        "missing_gate": "缺门禁",
        "violations": "违规数",
        "violation_rate": "违规率",
        "holding_risk": "持仓风险",
        "holding_exit": "需退出",
        "holding_reduce": "需减仓",
        "exit_sell_all": "清仓任务",
        "exit_reduce": "减仓任务",
        "lifecycle": "生命周期",
        "total": "总数",
        "pass": "通过",
    }
    return labels.get(key, key)
