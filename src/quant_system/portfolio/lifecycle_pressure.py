from __future__ import annotations

from typing import Any


def build_review_memory_pressure(
    *,
    lifecycle_snapshots: list[dict[str, Any]] | None = None,
    doctor_report: dict[str, Any] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    snapshots = list(lifecycle_snapshots or [])
    if limit > 0:
        snapshots = snapshots[-limit:]
    doctor_report = doctor_report or {}
    if not snapshots and not doctor_report:
        return {}

    statuses = [str(item.get("status", "") or "pass") for item in snapshots]
    severities = [_status_severity(status) for status in statuses]
    pressure_scores = [build_lifecycle_pressure(item).get("score", 100.0) for item in snapshots]
    block_count = sum(1 for status in statuses if status == "block")
    warn_count = sum(1 for status in statuses if status == "warn")
    pass_count = sum(1 for status in statuses if status == "pass")
    latest = snapshots[-1] if snapshots else {}
    latest_execution = dict(latest.get("execution") or {})
    trend = _severity_trend(severities, pressure_scores, snapshots)

    doctor_issues = list(doctor_report.get("issues", []) or [])
    doctor_status = str(doctor_report.get("status", "") or "")
    doctor_fail_count = sum(1 for item in doctor_issues if str(item.get("status", "")) == "fail")
    doctor_warn_count = sum(1 for item in doctor_issues if str(item.get("status", "")) == "warn")
    doctor_issue_names = [str(item.get("name", "")) for item in doctor_issues if str(item.get("name", ""))]

    alerts: list[str] = []
    score = 100.0
    alert_level = "pass"
    action = "keep"

    if block_count >= 2:
        score -= 28.0
        alert_level = "block"
        action = "pause"
        alerts.append("lifecycle_repeated_block")
    elif block_count or str(latest.get("status", "")) == "block":
        score -= 18.0
        alert_level = "block"
        action = "pause"
        alerts.append("lifecycle_recent_block")
    elif warn_count >= 2 or str(latest.get("status", "")) == "warn":
        score -= 12.0
        alert_level = "warn"
        action = "reduce"
        alerts.append("lifecycle_repeated_warn")

    if trend == "worsening":
        score -= 10.0
        if alert_level == "pass":
            alert_level = "warn"
        if action == "keep":
            action = "reduce"
        alerts.append("lifecycle_worsening")
    elif trend == "improving":
        score += 4.0

    rate_fields = (
        ("trade_plan_match_rate", "trade_plan_match_gap"),
        ("action_execution_rate", "action_execution_gap"),
        ("exit_execution_rate", "exit_execution_gap"),
        ("lot_exit_execution_rate", "lot_exit_execution_gap"),
    )
    averages = {key: _avg_execution_rate(snapshots, key) for key, _ in rate_fields}
    latest_rates = {key: _float_or_none(latest_execution.get(key)) for key, _ in rate_fields}
    for key, alert in rate_fields:
        average = averages[key]
        if average is None:
            continue
        if average < 0.7:
            score -= 10.0
            if alert_level == "pass":
                alert_level = "warn"
            if action == "keep":
                action = "reduce"
            alerts.append(alert)
        elif average < 0.85:
            score -= 4.0
            if alert_level == "pass":
                alert_level = "warn"
            alerts.append(f"{alert}_watch")

    if doctor_status == "fail" or doctor_fail_count:
        score -= 22.0
        alert_level = "block"
        action = "pause"
        alerts.append("review_doctor_fail")
    elif doctor_status == "warn" or doctor_warn_count:
        score -= min(doctor_warn_count * 5.0, 16.0)
        if alert_level == "pass":
            alert_level = "warn"
        if action == "keep":
            action = "reduce"
        alerts.append("review_doctor_warn")

    if "stale_lifecycle_snapshot" in doctor_issue_names:
        score -= 6.0
        if alert_level == "pass":
            alert_level = "warn"
        alerts.append("stale_lifecycle_snapshot")
    if "latest_exit_sell_all" in doctor_issue_names:
        score -= 8.0
        if alert_level == "pass":
            alert_level = "warn"
        if action == "keep":
            action = "reduce"
        alerts.append("latest_exit_sell_all")

    first_date = _snapshot_date(snapshots[0]) if snapshots else ""
    latest_date = _snapshot_date(snapshots[-1]) if snapshots else ""
    score = round(max(min(score, 100.0), 0.0), 2)
    return {
        "snapshot_count": len(lifecycle_snapshots or []),
        "window_count": len(snapshots),
        "first_snapshot_date": first_date,
        "latest_snapshot_date": latest_date,
        "latest_status": str(latest.get("status", "") or ""),
        "block_count": block_count,
        "warn_count": warn_count,
        "pass_count": pass_count,
        "status_trend": trend,
        "avg_trade_plan_match_rate": averages["trade_plan_match_rate"],
        "avg_action_execution_rate": averages["action_execution_rate"],
        "avg_exit_execution_rate": averages["exit_execution_rate"],
        "avg_lot_exit_execution_rate": averages["lot_exit_execution_rate"],
        "latest_trade_plan_match_rate": latest_rates["trade_plan_match_rate"],
        "latest_action_execution_rate": latest_rates["action_execution_rate"],
        "latest_exit_execution_rate": latest_rates["exit_execution_rate"],
        "latest_lot_exit_execution_rate": latest_rates["lot_exit_execution_rate"],
        "doctor_status": doctor_status,
        "doctor_issue_count": len(doctor_issues),
        "doctor_fail_count": doctor_fail_count,
        "doctor_warn_count": doctor_warn_count,
        "doctor_issue_names": doctor_issue_names,
        "score": score,
        "alert_level": alert_level,
        "action": action,
        "alerts": _unique(alerts),
        "summary": _review_memory_summary(
            window_count=len(snapshots),
            block_count=block_count,
            warn_count=warn_count,
            trend=trend,
            doctor_status=doctor_status,
            doctor_issue_count=len(doctor_issues),
            score=score,
        ),
    }


def build_lifecycle_pressure(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {}

    execution = snapshot.get("execution", {}) or {}
    lots = snapshot.get("lots", {}) or {}
    holding = snapshot.get("holding_actions", {}) or {}
    exit_plan = snapshot.get("exit_plan", {}) or {}
    status = str(snapshot.get("status", "pass") or "pass")

    alerts: list[str] = []
    score = 100.0
    action = "keep"
    alert_level = "pass"

    missed_actions = int(execution.get("action_missed_count", 0) or 0)
    missed_exits = int(execution.get("exit_missed_count", 0) or 0)
    missed_lot_exits = int(execution.get("lot_exit_missed_count", 0) or 0)
    sell_all_count = int(exit_plan.get("sell_all_count", 0) or 0)
    stale_lots = int(lots.get("stale_open_lots", 0) or 0)
    reduce_count = int(holding.get("reduce_count", 0) or 0)
    exit_count = int(holding.get("exit_count", 0) or 0)

    if status == "block" or missed_actions or missed_exits or missed_lot_exits or sell_all_count:
        alert_level = "block"
        action = "pause"
        alerts.append("lifecycle_block")
        score -= 25.0
        score -= min((missed_actions + missed_exits + missed_lot_exits) * 8.0, 24.0)
        score -= min(sell_all_count * 6.0, 18.0)
    elif status == "warn" or stale_lots or reduce_count or exit_count:
        alert_level = "warn"
        action = "reduce"
        alerts.append("lifecycle_drift")
        score -= 12.0
        score -= min(stale_lots * 4.0 + reduce_count * 3.0 + exit_count * 5.0, 18.0)

    score = _apply_rate_pressure(
        score,
        execution,
        "action_execution_rate",
        "action_actionable_count",
        alerts,
        "action_execution_gap",
    )
    score = _apply_rate_pressure(
        score,
        execution,
        "exit_execution_rate",
        "exit_actionable_count",
        alerts,
        "exit_execution_gap",
    )
    score = _apply_rate_pressure(
        score,
        execution,
        "lot_exit_execution_rate",
        "lot_exit_actionable_count",
        alerts,
        "lot_exit_execution_gap",
    )

    if any(alert in alerts for alert in ("action_execution_gap", "exit_execution_gap", "lot_exit_execution_gap")):
        if alert_level == "pass":
            alert_level = "warn"
        if action == "keep":
            action = "reduce"

    return {
        "status": status,
        "score": round(max(score, 0.0), 2),
        "alert_level": alert_level,
        "action": action,
        "alerts": _unique(alerts),
        "stale_open_lots": stale_lots,
        "exit_count": exit_count,
        "reduce_count": reduce_count,
        "sell_all_count": sell_all_count,
        "trade_plan_match_rate": _float(execution.get("trade_plan_match_rate")),
        "action_execution_rate": _float(execution.get("action_execution_rate")),
        "exit_execution_rate": _float(execution.get("exit_execution_rate")),
        "lot_exit_execution_rate": _float(execution.get("lot_exit_execution_rate")),
        "action_missed_count": missed_actions,
        "exit_missed_count": missed_exits,
        "lot_exit_missed_count": missed_lot_exits,
        "summary": lifecycle_pressure_summary(snapshot),
    }


def lifecycle_pressure_summary(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return ""
    execution = snapshot.get("execution", {}) or {}
    lots = snapshot.get("lots", {}) or {}
    exit_plan = snapshot.get("exit_plan", {}) or {}
    status = str(snapshot.get("status", "pass") or "pass")
    return (
        f"状态 {status}；计划命中 {float(execution.get('trade_plan_match_rate', 0) or 0):.1%}；"
        f"动作执行 {float(execution.get('action_execution_rate', 0) or 0):.1%}；"
        f"退出执行 {float(execution.get('exit_execution_rate', 0) or 0):.1%}；"
        f"批次退出 {float(execution.get('lot_exit_execution_rate', 0) or 0):.1%}；"
        f"陈旧批次 {int(lots.get('stale_open_lots', 0) or 0)}；"
        f"清仓任务 {int(exit_plan.get('sell_all_count', 0) or 0)}"
    )


def _apply_rate_pressure(
    score: float,
    execution: dict[str, Any],
    rate_key: str,
    count_key: str,
    alerts: list[str],
    alert: str,
) -> float:
    actionable_count = int(execution.get(count_key, 0) or 0)
    if actionable_count <= 0:
        return score
    rate = float(execution.get(rate_key, 0) or 0)
    if rate >= 1.0:
        return score
    alerts.append(alert)
    return score - min((1.0 - rate) * 20.0, 12.0)


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _avg_execution_rate(snapshots: list[dict[str, Any]], key: str) -> float | None:
    values = []
    for snapshot in snapshots:
        execution = snapshot.get("execution", {}) or {}
        value = execution.get(key)
        if value not in (None, ""):
            values.append(float(value))
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _snapshot_date(snapshot: dict[str, Any]) -> str:
    return str(snapshot.get("snapshot_date", "") or snapshot.get("created_at", "") or "")


def _status_severity(status: str) -> int:
    return {"pass": 0, "warn": 1, "block": 2, "fail": 2}.get(str(status or "pass"), 0)


def _severity_trend(severities: list[int], scores: list[float], snapshots: list[dict[str, Any]]) -> str:
    if len(severities) < 2:
        return "flat"
    delta = severities[-1] - severities[0]
    if delta >= 1:
        return "worsening"
    if delta <= -1:
        return "improving"
    if len(scores) >= 2:
        score_delta = float(scores[-1]) - float(scores[0])
        if score_delta <= -5:
            return "worsening"
        if score_delta >= 5:
            return "improving"
    first_quality = _execution_quality(snapshots[0])
    latest_quality = _execution_quality(snapshots[-1])
    if first_quality is not None and latest_quality is not None:
        quality_delta = latest_quality - first_quality
        if quality_delta <= -0.1:
            return "worsening"
        if quality_delta >= 0.1:
            return "improving"
    return "flat"


def _execution_quality(snapshot: dict[str, Any]) -> float | None:
    execution = snapshot.get("execution", {}) or {}
    values = [
        float(execution.get(key))
        for key in (
            "trade_plan_match_rate",
            "action_execution_rate",
            "exit_execution_rate",
            "lot_exit_execution_rate",
        )
        if execution.get(key) not in (None, "")
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _review_memory_summary(
    *,
    window_count: int,
    block_count: int,
    warn_count: int,
    trend: str,
    doctor_status: str,
    doctor_issue_count: int,
    score: float,
) -> str:
    return (
        f"window {window_count}; lifecycle block {block_count}, warn {warn_count}; "
        f"trend {trend}; doctor {doctor_status or '-'} with {doctor_issue_count} issues; "
        f"memory score {score:.1f}"
    )


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result
