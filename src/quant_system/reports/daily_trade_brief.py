from __future__ import annotations

from typing import Any


def build_daily_trade_brief(
    *,
    workflow_summary: dict[str, Any] | None = None,
    battle_plan: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
    assistant: dict[str, Any] | None = None,
    trade_plan_batch: Any | None = None,
    review_doctor: dict[str, Any] | None = None,
    review_attribution: dict[str, Any] | None = None,
    attribution_policy: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    workflow_summary = workflow_summary or {}
    battle_plan = battle_plan or {}
    cockpit = cockpit or {}
    assistant = assistant or {}
    review_doctor = review_doctor or {}
    review_attribution = review_attribution or {}
    attribution_policy = attribution_policy or {}
    outputs = outputs or {}
    limit = max(int(limit or 8), 1)

    status = _rollup_status(
        str(workflow_summary.get("status", "") or "ok"),
        str(battle_plan.get("status", "") or "pass"),
        str(cockpit.get("status", "") or "pass"),
        str(assistant.get("status", "") or "pass"),
        str(review_doctor.get("status", "") or "pass"),
        str(review_attribution.get("status", "") or "pass"),
        str(attribution_policy.get("status", "") or "pass"),
    )
    allowed = _allowed_orders(battle_plan, limit=limit)
    blocked = _blocked_orders(battle_plan, limit=limit)
    must_handle = _must_handle_items(battle_plan, assistant, cockpit, limit=limit)
    review_actions = _review_actions(review_doctor, review_attribution, attribution_policy, limit=limit)
    can_open_new_position = status not in {"block", "fail"} and bool(allowed)
    return {
        "status": status,
        "can_open_new_position": can_open_new_position,
        "decision": _decision(status, can_open_new_position),
        "target_exposure_pct": _float(battle_plan.get("target_exposure_pct")),
        "allocated_pct": _float(battle_plan.get("allocated_pct")),
        "allowed_orders": allowed,
        "blocked_orders": blocked,
        "must_handle": must_handle,
        "review_actions": review_actions,
        "counts": {
            "allowed_orders": len(allowed),
            "blocked_orders": len(blocked),
            "must_handle": len(must_handle),
            "review_actions": len(review_actions),
        },
        "next_commands": _next_commands(can_open_new_position, outputs),
        "outputs": dict(outputs),
    }


def render_daily_trade_brief_markdown(brief: dict[str, Any] | None) -> str:
    brief = brief or {}
    lines = [
        "# 今日交易主清单",
        "",
        f"- 总状态：{brief.get('status', '')}",
        f"- 能否开新仓：{'可以' if brief.get('can_open_new_position') else '不可以'}",
        f"- 结论：{brief.get('decision', '')}",
        f"- 目标仓位：{_pct(brief.get('target_exposure_pct'))}",
        f"- 已分配仓位：{_pct(brief.get('allocated_pct'))}",
        "",
        "## 先处理",
        "",
    ]
    must_handle = list(brief.get("must_handle") or [])
    if must_handle:
        lines.extend(f"- [{item.get('priority', '')}] {item.get('text', '')}" for item in must_handle)
    else:
        lines.append("- 暂无必须先处理事项。")

    lines.extend(["", "## 允许买入", ""])
    allowed = list(brief.get("allowed_orders") or [])
    if allowed:
        for item in allowed:
            lines.append(
                f"- [{item.get('status', '')}] {item.get('symbol', '')} {item.get('name', '')}: "
                f"最多 {_pct(item.get('allowed_pct'))}，计划 {_pct(item.get('planned_pct'))}，"
                f"入场 {_price(item.get('entry_price'))}，止损 {_price(item.get('stop_price'))}，"
                f"目标 {_price(item.get('target_price'))}"
            )
    else:
        lines.append("- 当前没有允许买入的候选。")

    lines.extend(["", "## 禁止或观察", ""])
    blocked = list(brief.get("blocked_orders") or [])
    if blocked:
        for item in blocked:
            lines.append(f"- {item.get('symbol', '')} {item.get('name', '')}: {item.get('reason', '')}")
    else:
        lines.append("- 暂无禁止或观察候选。")

    lines.extend(["", "## 盘后复盘入口", ""])
    review_actions = list(brief.get("review_actions") or [])
    if review_actions:
        lines.extend(f"- {item}" for item in review_actions)
    else:
        lines.append("- 盘后按正常成交回写、执行审计、复盘归因顺序检查。")

    lines.extend(["", "## 下一步命令", ""])
    for command in list(brief.get("next_commands") or []):
        lines.append(f"- `{command}`")
    return "\n".join(lines)


def _allowed_orders(plan: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    orders = []
    for item in list(plan.get("buy_candidates") or []):
        row = dict(item)
        row["status"] = str(row.get("status", "") or "pass")
        orders.append(row)
    return orders[:limit]


def _blocked_orders(plan: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    orders = []
    for item in list(plan.get("blocked_candidates") or []):
        row = dict(item)
        row["reason"] = str(row.get("reason", "") or "最终作战单阻断。")
        orders.append(row)
    return orders[:limit]


def _must_handle_items(
    battle_plan: dict[str, Any],
    assistant: dict[str, Any],
    cockpit: dict[str, Any],
    *,
    limit: int,
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in list(battle_plan.get("must_do") or []):
        items.append({"priority": str(item.get("priority", "P0") or "P0"), "text": str(item.get("text", "") or "")})
    for item in list(assistant.get("urgent_actions") or []):
        items.append({"priority": str(item.get("priority", "P1") or "P1"), "text": str(item.get("text", "") or "")})
    for item in list(cockpit.get("action_items") or []):
        items.append({"priority": str(item.get("priority", "P1") or "P1"), "text": str(item.get("text", "") or "")})
    return _dedupe_items(items)[:limit]


def _review_actions(
    review_doctor: dict[str, Any],
    review_attribution: dict[str, Any],
    attribution_policy: dict[str, Any],
    *,
    limit: int,
) -> list[str]:
    items: list[str] = []
    items.extend(str(item) for item in list(review_doctor.get("action_items") or []) if str(item))
    items.extend(str(item) for item in list(review_attribution.get("action_items") or []) if str(item))
    items.extend(str(item) for item in list(attribution_policy.get("action_items") or []) if str(item))
    return _dedupe_text(items)[:limit]


def _next_commands(can_open_new_position: bool, outputs: dict[str, Any]) -> list[str]:
    commands = []
    if can_open_new_position:
        commands.append("python -m quant_system portfolio approve --symbol 000001 --current-price 0 --planned-pct 0.00 --record")
    commands.extend(
        [
            "python -m quant_system review trade-add --symbol 000001 --side BUY --price 0 --quantity 0 --reason \"按审批执行\"",
            "python -m quant_system review attribution --format markdown --output reports/review_attribution.md",
        ]
    )
    if outputs.get("summary"):
        commands.append(f"查看工作流摘要：{outputs['summary']}")
    return commands


def _decision(status: str, can_open_new_position: bool) -> str:
    if status in {"fail", "block"}:
        return "禁止新增买入；先处理阻断、数据或复盘缺口。"
    if status == "warn":
        return "只允许计划内、降仓、显式审批后的交易。"
    if can_open_new_position:
        return "可以按最终作战单执行，但每笔订单仍需先走下单审批。"
    return "流程通过，但当前没有可执行买入候选。"


def _rollup_status(*statuses: str) -> str:
    if "fail" in statuses:
        return "fail"
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _dedupe_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in sorted(items, key=lambda row: row.get("priority", "P9")):
        text = str(item.get("text", "") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(item)
    return result


def _dedupe_text(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


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
