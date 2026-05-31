from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


def build_approval_cooldown_constraints(
    audit_summary: dict[str, Any] | None,
    *,
    source: str = "review.approval-audit",
    default_strategy: str = "manual_order",
    block_threshold: int = 1,
    warn_threshold: int = 2,
    fallback_threshold: int = 2,
    warn_exposure_multiplier: float = 0.5,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    summary = audit_summary or {}
    records = list(summary.get("records") or [])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        strategy = str(record.get("strategy", "") or default_strategy).strip() or default_strategy
        grouped[strategy].append(record)

    constraints: list[dict[str, Any]] = []
    stamp = created_at or datetime.now(timezone.utc).isoformat()
    for strategy, items in sorted(grouped.items()):
        constraint = _constraint_for_group(
            strategy,
            items,
            source=source,
            created_at=stamp,
            block_threshold=max(int(block_threshold), 1),
            warn_threshold=max(int(warn_threshold), 1),
            fallback_threshold=max(int(fallback_threshold), 1),
            warn_exposure_multiplier=max(min(float(warn_exposure_multiplier), 1.0), 0.0),
        )
        if constraint is not None:
            constraints.append(constraint)
    return constraints


def render_approval_cooldown_markdown(payload: dict[str, Any] | None) -> str:
    payload = payload or {}
    constraints = list(payload.get("constraints") or [])
    lines = [
        "# 审批冷静期",
        "",
        f"- 状态：{payload.get('status', 'pass')}",
        f"- 约束数量：{len(constraints)}",
        f"- 来源：{payload.get('source', 'review.approval-audit')}",
        "",
    ]
    if constraints:
        lines.extend(["| 策略 | 告警 | 动作 | 仓位乘数 | 标签 |", "| --- | --- | --- | ---: | --- |"])
        for item in constraints:
            lines.append(
                f"| {item.get('strategy', '')} | {item.get('alert_level', '')} | {item.get('action', '')} | "
                f"{float(item.get('exposure_multiplier', 0) or 0):.2f} | {', '.join(list(item.get('alerts') or []))} |"
            )
            lines.append(f"  - {item.get('note', '')}")
    else:
        lines.append("- 未生成审批冷静期约束。")
    action_items = list(payload.get("action_items") or [])
    if action_items:
        lines.extend(["", "## 处理动作", ""])
        lines.extend(f"- {item}" for item in action_items)
    return "\n".join(lines)


def summarize_approval_cooldown(constraints: list[dict[str, Any]], *, source: str = "review.approval-audit") -> dict[str, Any]:
    level_counts = Counter(str(item.get("alert_level", "") or "") for item in constraints)
    status = "block" if level_counts.get("block", 0) else ("warn" if level_counts.get("warn", 0) else "pass")
    return {
        "status": status,
        "source": source,
        "constraint_count": len(constraints),
        "by_alert_level": dict(level_counts),
        "constraints": constraints,
        "action_items": _summary_action_items(constraints),
    }


def _constraint_for_group(
    strategy: str,
    records: list[dict[str, Any]],
    *,
    source: str,
    created_at: str,
    block_threshold: int,
    warn_threshold: int,
    fallback_threshold: int,
    warn_exposure_multiplier: float,
) -> dict[str, Any] | None:
    block_records = [record for record in records if str(record.get("status", "") or "") == "block"]
    warn_records = [record for record in records if str(record.get("status", "") or "") == "warn"]
    fallback_records = [record for record in records if str(record.get("linked_by", "") or "") == "fallback_symbol_date"]
    if not block_records and len(warn_records) < warn_threshold and len(fallback_records) < fallback_threshold:
        return None

    alerts = _alerts_for_records(records)
    symbols = _top_symbols(records)
    symbol = symbols[0] if len(symbols) == 1 else ""
    if len(block_records) >= block_threshold:
        alert_level = "block"
        action = "pause"
        exposure_multiplier = 0.0
        alerts = _dedupe([*alerts, "approval_cooldown", "approval_block"])
        note = (
            f"审批执行审计发现 {strategy} 存在 {len(block_records)} 条阻断级违规。"
            "在完成复核并生成干净的审批审计前，暂停新增 BUY。"
        )
    else:
        alert_level = "warn"
        action = "reduce"
        exposure_multiplier = warn_exposure_multiplier
        alerts = _dedupe([*alerts, "approval_warn"])
        note = (
            f"审批执行审计发现 {strategy} 存在 {len(warn_records)} 条预警和 {len(fallback_records)} 条兜底匹配。"
            f"将仓位乘数降至 {warn_exposure_multiplier:.2f}，并要求显式绑定订单审批。"
        )
    return {
        "created_at": created_at,
        "source": source,
        "strategy": strategy,
        "symbol": symbol,
        "alert_level": alert_level,
        "action": action,
        "alerts": alerts,
        "note": note,
        "exposure_multiplier": exposure_multiplier,
        "approval_audit": {
            "record_count": len(records),
            "block_count": len(block_records),
            "warn_count": len(warn_records),
            "fallback_link_count": len(fallback_records),
            "symbols": symbols,
        },
    }


def _alerts_for_records(records: list[dict[str, Any]]) -> list[str]:
    alerts: list[str] = []
    for record in records:
        audit_type = str(record.get("audit_type", "") or "")
        linked_by = str(record.get("linked_by", "") or "")
        approval_status = str(record.get("approval_status", "") or "")
        status = str(record.get("status", "") or "")
        reasons = " ".join(str(item) for item in list(record.get("reasons") or []))
        if audit_type == "orphan_trade":
            alerts.append("missing_order_approval")
        if approval_status == "block" and status == "block":
            alerts.append("block_approval_executed")
        if "exceeded approved quantity" in reasons:
            alerts.append("approval_quantity_exceeded")
        if "exceeded approved value" in reasons:
            alerts.append("approval_value_exceeded")
        if linked_by == "fallback_symbol_date":
            alerts.append("approval_fallback_link")
        if "no matching BUY trade" in reasons:
            alerts.append("approval_not_executed")
        if "no review note" in reasons:
            alerts.append("approval_review_missing")
    return _dedupe(alerts)


def _top_symbols(records: list[dict[str, Any]]) -> list[str]:
    counts = Counter(str(record.get("symbol", "") or "") for record in records if record.get("symbol"))
    return [symbol for symbol, _count in counts.most_common(5)]


def _summary_action_items(constraints: list[dict[str, Any]]) -> list[str]:
    if not constraints:
        return ["审批纪律当前干净；继续要求每笔成交绑定最终审批。"]
    if any(str(item.get("alert_level", "") or "") == "block" for item in constraints):
        return ["存在阻断级审批冷静期；明日盘前应暂停受影响策略，直到完成复核。"]
    return ["存在预警级审批冷静期；受影响策略降低仓位，并要求每笔成交显式绑定审批。"]


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in result:
            result.append(value)
    return result
