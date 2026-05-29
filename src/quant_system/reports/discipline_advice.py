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
    missing_gate_count = int(gate_review.get("missing_gate_count", 0) or 0)
    if violation_count:
        lines.append(
            f"- Tomorrow gate rule: review {violation_count} warn/block BUY record(s) before any new buy; only planned confirmation trades are allowed."
        )
    if missing_gate_count:
        lines.append(f"- Logging rule: {missing_gate_count} trade(s) missed gate snapshots; attach workflow summary or manual gate fields next time.")

    avg_deviation = float(trade_stats.get("avg_execution_deviation_pct", 0) or 0)
    if abs(avg_deviation) >= 0.02:
        lines.append(
            f"- Execution rule: average execution deviation is {avg_deviation:.2%}; use planned price bands and record exception reasons before entry."
        )
    exception_count = int(trade_stats.get("discipline_exception_count", 0) or 0)
    if exception_count:
        lines.append(
            f"- Exception rule: {exception_count} trade(s) used discipline exceptions; keep exception reasons explicit and do not let exceptions become the default path."
        )
    if trade_stats.get("mistake_counts"):
        top_mistake = _top_item(trade_stats.get("mistake_counts", {}))
        if top_mistake:
            lines.append(f"- Mistake focus: '{top_mistake[0]}' appeared {top_mistake[1]} time(s); make it tomorrow's single review theme.")

    risk_status = str(holding_risk.get("status", "") or "")
    if risk_status == "block":
        lines.append("- Holding rule: portfolio risk is blocking; no new positions until stop/exposure issues are handled.")
    elif risk_status == "warn":
        lines.append("- Holding rule: portfolio risk is warning; cut position size and avoid adding to existing risk.")

    target = float(allocation_plan.get("target_exposure_pct", 0) or 0)
    allocated = float(allocation_plan.get("allocated_pct", 0) or 0)
    if target > 0 and allocated > target * 1.05:
        lines.append(f"- Exposure rule: allocated exposure {allocated:.1%} is above target {target:.1%}; trim or pause new buys.")
    elif target == 0 and allocated > 0:
        lines.append(f"- Exposure rule: target exposure is 0.0% but allocated exposure is {allocated:.1%}; prioritize de-risking.")

    if not lines:
        lines.append("- Discipline rule: no critical discipline issue detected; keep precheck, gate snapshot, and trade journal complete.")
    return lines


def _top_item(values: dict | None) -> tuple[str, int] | None:
    items = [(str(key), int(value)) for key, value in (values or {}).items() if str(key)]
    if not items:
        return None
    return sorted(items, key=lambda item: (-item[1], item[0]))[0]
