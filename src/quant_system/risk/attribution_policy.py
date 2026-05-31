from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any


def build_attribution_policy(
    attribution_report: dict[str, Any] | None,
    *,
    default_strategy: str = "manual_order",
    effective_date: str = "",
    warn_exposure_multiplier: float = 0.5,
    created_at: str | None = None,
) -> dict[str, Any]:
    report = attribution_report or {}
    causes = list(report.get("root_causes") or [])
    stamp = created_at or datetime.now(timezone.utc).isoformat()
    session_date = effective_date or date.today().isoformat()
    grouped = _group_causes_by_area(causes)
    constraints = [
        _constraint_for_area(
            area,
            items,
            default_strategy=default_strategy,
            effective_date=session_date,
            warn_exposure_multiplier=warn_exposure_multiplier,
            created_at=stamp,
        )
        for area, items in sorted(grouped.items())
    ]
    constraints = [item for item in constraints if item is not None]
    status = _rollup_status([str(item.get("alert_level", "")) for item in constraints]) or str(report.get("status", "pass") or "pass")
    discipline_record = _discipline_record(
        report,
        constraints,
        status=status,
        effective_date=session_date,
        created_at=stamp,
    )
    return {
        "status": status,
        "effective_date": session_date,
        "constraint_count": len(constraints),
        "constraints": constraints,
        "discipline_record": discipline_record,
        "action_items": _action_items(status, constraints),
        "attribution": {
            "status": report.get("status", "pass"),
            "score": report.get("score", 100),
            "root_cause_count": report.get("root_cause_count", len(causes)),
            "by_area": report.get("by_area", {}),
        },
    }


def render_attribution_policy_markdown(policy: dict[str, Any] | None) -> str:
    policy = policy or {}
    constraints = list(policy.get("constraints") or [])
    discipline = dict(policy.get("discipline_record") or {})
    lines = [
        "# Attribution Policy",
        "",
        f"- Status: {policy.get('status', 'pass')}",
        f"- Effective date: {policy.get('effective_date', '') or '-'}",
        f"- Constraint count: {len(constraints)}",
        "",
        "## Next-Day Constraints",
        "",
    ]
    if constraints:
        lines.extend(["| Area | Alert | Action | Multiplier | Alerts |", "| --- | --- | --- | ---: | --- |"])
        for item in constraints:
            lines.append(
                f"| {item.get('attribution_area', '')} | {item.get('alert_level', '')} | {item.get('action', '')} | "
                f"{float(item.get('exposure_multiplier', 0) or 0):.2f} | {', '.join(list(item.get('alerts') or []))} |"
            )
            lines.append(f"  - {item.get('note', '')}")
    else:
        lines.append("- No next-day constraint is required.")

    advice = list(discipline.get("advice") or [])
    lines.extend(["", "## Discipline Advice", ""])
    if advice:
        lines.extend(f"- {item}" for item in advice)
    else:
        lines.append("- Attribution is clean; keep the normal plan-confirm-approve-trade-review chain.")

    action_items = list(policy.get("action_items") or [])
    if action_items:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in action_items)
    return "\n".join(lines)


def _group_causes_by_area(causes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in causes:
        area = str(item.get("area", "") or "general")
        grouped[area].append(item)
    return grouped


def _constraint_for_area(
    area: str,
    causes: list[dict[str, Any]],
    *,
    default_strategy: str,
    effective_date: str,
    warn_exposure_multiplier: float,
    created_at: str,
) -> dict[str, Any] | None:
    if not causes:
        return None
    level = "block" if any(str(item.get("severity", "")) == "block" for item in causes) else "warn"
    action = "pause" if level == "block" else "reduce"
    multiplier = 0.0 if level == "block" else max(min(float(warn_exposure_multiplier), 1.0), 0.0)
    signals = _dedupe([str(item.get("signal", "")) for item in causes])
    alerts = _dedupe([f"attribution_{area}", *signals])
    evidence = "; ".join(str(item.get("evidence", "")) for item in causes if str(item.get("evidence", "")))[:240]
    return {
        "created_at": created_at,
        "source": "review.attribution",
        "strategy": default_strategy,
        "symbol": "",
        "alert_level": level,
        "action": action,
        "alerts": alerts,
        "note": _note(area, level, effective_date, evidence),
        "exposure_multiplier": multiplier,
        "effective_date": effective_date,
        "attribution_area": area,
        "root_cause_signals": signals,
        "root_cause_count": len(causes),
    }


def _discipline_record(
    report: dict[str, Any],
    constraints: list[dict[str, Any]],
    *,
    status: str,
    effective_date: str,
    created_at: str,
) -> dict[str, Any]:
    summary = dict(report.get("summary") or {})
    return {
        "created_at": created_at,
        "date": effective_date,
        "source": "review.attribution-policy",
        "status": status,
        "advice": _discipline_advice(status, constraints),
        "gate_violation_count": int(summary.get("gate_violations", 0) or 0),
        "missing_gate_count": 0,
        "avg_execution_deviation_pct": 0.0,
        "mistake_counts": {},
        "holding_status": str(summary.get("lifecycle_status", "") or ""),
        "target_exposure_pct": 0.0 if status == "block" else 0.5 if status == "warn" else 1.0,
        "allocated_pct": 0.0,
        "attribution": report,
        "constraints": constraints,
    }


def _discipline_advice(status: str, constraints: list[dict[str, Any]]) -> list[str]:
    if not constraints:
        return ["Attribution is clean; keep the same trading process tomorrow."]
    advice: list[str] = []
    if status == "block":
        advice.append("Start the next session in no-new-BUY mode until all block-level attribution constraints are cleared.")
    elif status == "warn":
        advice.append("Use reduced exposure and require explicit exception notes for any warn-level trade.")
    for item in constraints:
        area = str(item.get("attribution_area", "") or "general")
        action = str(item.get("action", "") or "")
        advice.append(f"{area}: {action} affected strategy until the listed root cause is reviewed.")
    return _dedupe(advice)


def _action_items(status: str, constraints: list[dict[str, Any]]) -> list[str]:
    if not constraints:
        return ["No attribution policy constraint is required for the next session."]
    items = []
    if status == "block":
        items.append("Before the next open, clear or explicitly accept every block-level attribution constraint.")
    else:
        items.append("Before the next open, size down and review every warn-level attribution constraint.")
    items.append("Persist the generated constraints if they should affect strategy health and pretrade sizing.")
    return items


def _note(area: str, level: str, effective_date: str, evidence: str) -> str:
    prefix = "Pause new BUY orders" if level == "block" else "Reduce exposure"
    suffix = f" Evidence: {evidence}" if evidence else ""
    return f"{prefix} for attribution area '{area}' on {effective_date}.{suffix}"


def _rollup_status(levels: list[str]) -> str:
    if "block" in levels:
        return "block"
    if "warn" in levels:
        return "warn"
    return "pass"


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        value = str(item or "").strip()
        if value and value not in result:
            result.append(value)
    return result
