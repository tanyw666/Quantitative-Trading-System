from __future__ import annotations


def render_discipline_advice_lines(
    *,
    gate_review: dict | None = None,
    trade_stats: dict | None = None,
    holding_risk: dict | None = None,
    allocation_plan: dict | None = None,
) -> list[str]:
    lines: list[str] = []
    gate_review = gate_review or {}
    trade_stats = trade_stats or {}
    holding_risk = holding_risk or {}
    allocation_plan = allocation_plan or {}

    violation_count = int(gate_review.get("violation_count", 0) or 0)
    structure_violation_count = int(gate_review.get("structure_violation_count", 0) or 0)
    missing_gate_count = int(gate_review.get("missing_gate_count", 0) or 0)
    if violation_count:
        lines.append(
            f"- 明日门禁规则：新增买入前先复核 {violation_count} 笔预警/阻断买入记录；只允许计划内确认单。"
        )
    if structure_violation_count:
        top_structure = _top_item(gate_review.get("by_structure_reason", {}) or {})
        focus = f"; focus={top_structure[0]}" if top_structure else ""
        lines.append(
            f"- Structure rule: {structure_violation_count} BUY records hit structure-gate warnings{focus}; next session blocks chase/false-breakout entries until a clean pretrade is regenerated."
        )
    if missing_gate_count:
        lines.append(f"- 记录规则：有 {missing_gate_count} 笔交易缺少门禁快照；下次必须补充 workflow 摘要或手动门禁字段。")

    avg_deviation = float(trade_stats.get("avg_execution_deviation_pct", 0) or 0)
    if abs(avg_deviation) >= 0.02:
        lines.append(
            f"- 执行规则：平均执行偏差为 {avg_deviation:.2%}；下单前要设计划价格带，并明确记录例外原因。"
        )
    exception_count = int(trade_stats.get("discipline_exception_count", 0) or 0)
    if exception_count:
        lines.append(
            f"- 例外规则：有 {exception_count} 笔交易使用了纪律例外；例外原因必须写清，不能把例外走成默认路径。"
        )
    if exception_count >= 2:
        lines.append("- Cooldown rule: discipline exceptions are becoming frequent; next session only allows trial-size entries with explicit approval evidence.")
    if trade_stats.get("mistake_counts"):
        top_mistake = _top_item(trade_stats.get("mistake_counts", {}))
        if top_mistake:
            lines.append(f"- 错误聚焦：'{top_mistake[0]}' 出现了 {top_mistake[1]} 次；把它设成明天唯一重点复盘项。")

    if trade_stats.get("emotion_counts"):
        top_emotion = _top_item(trade_stats.get("emotion_counts", {}))
        if top_emotion:
            lines.append(
                f"- Emotion rule: '{top_emotion[0]}' appeared {top_emotion[1]} time(s); next session requires smaller size and an explicit pre-order reason."
            )

    risk_status = str(holding_risk.get("status", "") or "")
    if risk_status == "block":
        lines.append("- 持仓规则：组合风险处于阻断状态；先处理止损或总暴露问题，再考虑新开仓。")
    elif risk_status == "warn":
        lines.append("- 持仓规则：组合风险处于预警状态；先降仓，避免继续往已有风险上加码。")

    target = float(allocation_plan.get("target_exposure_pct", 0) or 0)
    allocated = float(allocation_plan.get("allocated_pct", 0) or 0)
    if target > 0 and allocated > target * 1.05:
        lines.append(f"- 暴露规则：当前分配暴露 {allocated:.1%} 高于目标 {target:.1%}；应减仓或暂停新增买入。")
    elif target == 0 and allocated > 0:
        lines.append(f"- 暴露规则：目标暴露为 0.0%，但当前仍分配了 {allocated:.1%}；优先去风险。")

    if not lines:
        lines.append("- 纪律规则：当前没有关键纪律问题；继续把 precheck、门禁快照和交易日志记完整。")
    return lines


def _top_item(values: dict | None) -> tuple[str, int] | None:
    items = [(str(key), int(value)) for key, value in (values or {}).items() if str(key)]
    if not items:
        return None
    return sorted(items, key=lambda item: (-item[1], item[0]))[0]
