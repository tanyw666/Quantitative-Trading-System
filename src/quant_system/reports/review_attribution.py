from __future__ import annotations

from typing import Any


def build_review_attribution_report(
    *,
    trade_plan_audit: dict[str, Any] | None = None,
    execution_audit: dict[str, Any] | None = None,
    approval_audit: dict[str, Any] | None = None,
    approval_cooldown: dict[str, Any] | None = None,
    gate_review: dict[str, Any] | None = None,
    trade_stats: dict[str, Any] | None = None,
    lifecycle_snapshot: dict[str, Any] | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    trade_plan_audit = trade_plan_audit or {}
    execution_audit = execution_audit or {}
    approval_audit = approval_audit or {}
    approval_cooldown = approval_cooldown or {}
    gate_review = gate_review or {}
    trade_stats = trade_stats or {}
    lifecycle_snapshot = lifecycle_snapshot or {}

    root_causes: list[dict[str, Any]] = []
    root_causes.extend(_planning_causes(trade_plan_audit))
    root_causes.extend(_execution_causes(execution_audit))
    root_causes.extend(_approval_causes(approval_audit, approval_cooldown))
    root_causes.extend(_gate_causes(gate_review))
    root_causes.extend(_review_causes(trade_stats, lifecycle_snapshot))
    root_causes = sorted(root_causes, key=lambda item: (_severity_rank(item["severity"]), item["area"], item["signal"]))[: max(int(limit), 1)]

    status = _rollup_status([item["severity"] for item in root_causes])
    score = _score(root_causes)
    return {
        "status": status,
        "score": score,
        "root_cause_count": len(root_causes),
        "by_area": _by_area(root_causes),
        "root_causes": root_causes,
        "summary": {
            "trade_plan_match_rate": trade_plan_audit.get("match_rate", 0),
            "execution_blocks": int(execution_audit.get("block_count", 0) or 0),
            "approval_blocks": int(approval_audit.get("block_count", 0) or 0),
            "approval_cooldown_status": approval_cooldown.get("status", "pass"),
            "gate_violations": int(gate_review.get("violation_count", 0) or 0),
            "lifecycle_status": lifecycle_snapshot.get("status", ""),
        },
        "action_items": _action_items(root_causes, status),
    }


def render_review_attribution_markdown(report: dict[str, Any] | None) -> str:
    report = report or {}
    lines = [
        "# 复盘归因",
        "",
        f"- 状态：{report.get('status', 'pass')}",
        f"- 评分：{int(report.get('score', 100) or 0)}",
        f"- 根因数：{int(report.get('root_cause_count', 0) or 0)}",
        f"- 按领域分布：{report.get('by_area', {})}",
        "",
        "## 根因明细",
        "",
    ]
    causes = list(report.get("root_causes") or [])
    if causes:
        lines.extend(["| 严重级别 | 领域 | 信号 | 证据 | 下一步动作 |", "| --- | --- | --- | --- | --- |"])
        for item in causes:
            lines.append(
                f"| {item.get('severity', '')} | {item.get('area', '')} | {item.get('signal', '')} | "
                f"{item.get('evidence', '')} | {item.get('next_action', '')} |"
            )
    else:
        lines.append("- 当前样本没有明显的归因问题。")
    action_items = list(report.get("action_items") or [])
    if action_items:
        lines.extend(["", "## 行动项", ""])
        lines.extend(f"- {item}" for item in action_items)
    return "\n".join(lines)


def _planning_causes(summary: dict[str, Any]) -> list[dict[str, Any]]:
    causes: list[dict[str, Any]] = []
    total = int(summary.get("total_plans", 0) or 0)
    if total <= 0:
        return causes
    match_rate = float(summary.get("match_rate", 0) or 0)
    matched = int(summary.get("matched_trades", 0) or (1 if match_rate > 0 else 0))
    unmatched = int(summary.get("unmatched_plans", 0) or 0)
    orphan = int(summary.get("orphan_trades", 0) or 0)
    avg_price_deviation = float(summary.get("avg_price_deviation_pct", 0) or 0)
    if orphan >= 2 or (matched > 0 and match_rate < 0.7):
        causes.append(_cause("block", "planning", "trade_plan_mismatch", f"match_rate={match_rate:.1%}, orphan_trades={orphan}", "暂停该策略，直到每一笔 BUY 都能绑定到对应计划。"))
    elif match_rate < 0.85 or unmatched or orphan:
        causes.append(_cause("warn", "planning", "trade_plan_drift", f"match_rate={match_rate:.1%}, unmatched={unmatched}, orphan={orphan}", "下一个交易日前复核所有未成交计划和无计划成交。"))
    if abs(avg_price_deviation) > 0.03:
        causes.append(_cause("warn", "planning", "price_execution_window", f"avg_price_deviation={avg_price_deviation:.2%}", "收紧买入价窗口，或降低追价容忍度。"))
    return causes


def _execution_causes(summary: dict[str, Any]) -> list[dict[str, Any]]:
    causes: list[dict[str, Any]] = []
    block_count = int(summary.get("block_count", 0) or 0)
    warn_count = int(summary.get("warn_count", 0) or 0)
    missing_writeback = int(summary.get("missing_trade_writeback_count", 0) or 0)
    missing_confirmation = int(summary.get("missing_confirmation_trade_count", 0) or 0)
    if block_count:
        causes.append(_cause("block", "execution", "execution_block", f"block_count={block_count}", "执行偏差未复核前，停止新增 BUY。"))
    elif warn_count:
        causes.append(_cause("warn", "execution", "execution_warn", f"warn_count={warn_count}", "降低仓位，并检查成交价、数量和复盘备注。"))
    if missing_writeback:
        causes.append(_cause("warn", "execution", "missing_trade_writeback", f"missing_writebacks={missing_writeback}", "补记成交，或把确认单标记为跳过/取消。"))
    if missing_confirmation:
        causes.append(_cause("block", "execution", "missing_execution_confirmation", f"missing_confirmations={missing_confirmation}", "任何新增 BUY 前，必须先完成组合确认。"))
    return causes


def _approval_causes(approval_audit: dict[str, Any], cooldown: dict[str, Any]) -> list[dict[str, Any]]:
    causes: list[dict[str, Any]] = []
    block_count = int(approval_audit.get("block_count", 0) or 0)
    warn_count = int(approval_audit.get("warn_count", 0) or 0)
    missing_approval = int(approval_audit.get("missing_approval_trade_count", 0) or 0)
    fallback_links = int(approval_audit.get("fallback_link_count", 0) or 0)
    cooldown_status = str(cooldown.get("status", "") or "pass")
    if block_count or cooldown_status == "block":
        causes.append(_cause("block", "approval", "approval_cooldown_block", f"approval_blocks={block_count}, cooldown={cooldown_status}", "暂停相关策略，直到审批审计恢复干净。"))
    elif warn_count or cooldown_status == "warn":
        causes.append(_cause("warn", "approval", "approval_warning", f"approval_warns={warn_count}, cooldown={cooldown_status}", "降低暴露，并强制显式绑定审批记录。"))
    if missing_approval:
        causes.append(_cause("block", "approval", "missing_order_approval", f"missing_approval_trades={missing_approval}", "没有最终审批的 BUY 记录一律不接受。"))
    if fallback_links:
        causes.append(_cause("warn", "approval", "fallback_approval_link", f"fallback_links={fallback_links}", "写交易日志时补上 approval id。"))
    return causes


def _gate_causes(summary: dict[str, Any]) -> list[dict[str, Any]]:
    violations = int(summary.get("violation_count", 0) or 0)
    block_buys = int((summary.get("buy_status_counts") or {}).get("block", 0) or 0)
    missing_gate = int(summary.get("missing_gate_count", 0) or 0)
    causes: list[dict[str, Any]] = []
    if block_buys:
        causes.append(_cause("block", "gate", "block_gate_buy", f"block_gate_buys={block_buys}", "冻结新增风险，并复核为何会放行阻断门禁下的 BUY。"))
    elif violations:
        causes.append(_cause("warn", "gate", "warn_gate_buy", f"gate_violations={violations}", "所有预警门禁下的 BUY 都必须填写明确例外理由。"))
    if missing_gate:
        causes.append(_cause("warn", "gate", "missing_gate_context", f"missing_gate_records={missing_gate}", "把门禁状态写入每一笔交易记录。"))
    return causes


def _review_causes(trade_stats: dict[str, Any], lifecycle: dict[str, Any]) -> list[dict[str, Any]]:
    causes: list[dict[str, Any]] = []
    mistake_counts = dict(trade_stats.get("mistake_counts") or {})
    if mistake_counts:
        top_mistake, count = sorted(mistake_counts.items(), key=lambda item: (-int(item[1]), str(item[0])))[0]
        if int(count) >= 2:
            causes.append(_cause("warn", "behavior", "repeated_mistake", f"{top_mistake}={count}", "把这个高频错误固化成盘前检查规则。"))
    if int(trade_stats.get("discipline_exception_count", 0) or 0) > 0:
        causes.append(_cause("warn", "behavior", "discipline_exception", f"exceptions={trade_stats.get('discipline_exception_count')}", "逐笔复核纪律例外，判断是否真的合理。"))
    lifecycle_status = str(lifecycle.get("status", "") or "")
    if lifecycle_status == "block":
        causes.append(_cause("block", "lifecycle", "lifecycle_block", "latest lifecycle snapshot is block", "先补齐生命周期执行缺口，再考虑新增风险。"))
    elif lifecycle_status == "warn":
        causes.append(_cause("warn", "lifecycle", "lifecycle_warn", "latest lifecycle snapshot is warn", "先处理生命周期预警，再提高暴露。"))
    return causes


def _cause(severity: str, area: str, signal: str, evidence: str, next_action: str) -> dict[str, str]:
    return {
        "severity": severity,
        "area": area,
        "signal": signal,
        "evidence": evidence,
        "next_action": next_action,
    }


def _rollup_status(severities: list[str]) -> str:
    if "block" in severities:
        return "block"
    if "warn" in severities:
        return "warn"
    return "pass"


def _score(root_causes: list[dict[str, Any]]) -> int:
    score = 100
    for item in root_causes:
        score -= 25 if item.get("severity") == "block" else 10
    return max(score, 0)


def _by_area(root_causes: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in root_causes:
        area = str(item.get("area", "") or "unknown")
        counts[area] = counts.get(area, 0) + 1
    return counts


def _action_items(root_causes: list[dict[str, Any]], status: str) -> list[str]:
    if not root_causes:
        return ["当前归因干净，明天继续保持“计划-确认-审批-成交-复盘”这条链路。"]
    items: list[str] = []
    for item in root_causes:
        text = str(item.get("next_action", "") or "")
        if text and text not in items:
            items.append(text)
    if status == "block":
        items.insert(0, "明天先进入“禁止新增 BUY”模式，直到阻断级归因项被清理完成。")
    return items[:8]


def _severity_rank(severity: str) -> int:
    return {"block": 0, "warn": 1, "pass": 2}.get(str(severity), 3)
