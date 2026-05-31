from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any


def build_trading_day_watchdog(
    records: list[dict[str, Any]],
    *,
    as_of: str | date | datetime | None = None,
    repeat_threshold: int = 2,
    stale_days: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    as_of_date = _as_date(as_of) or date.today()
    sorted_records = sorted(list(records or []), key=lambda item: (str(item.get("date", "") or ""), str(item.get("created_at", "") or "")))
    visible_limit = max(int(limit), 0)
    recent = sorted_records[-visible_limit:] if visible_limit else sorted_records
    latest = sorted_records[-1] if sorted_records else {}
    today_records = [record for record in sorted_records if _as_date(record.get("date")) == as_of_date]
    current = today_records[-1] if today_records else latest
    alerts: list[dict[str, Any]] = []

    if not sorted_records:
        alerts.append(_alert("warn", "no_state_history", "No trading-day state records exist yet."))
    elif not today_records:
        alerts.append(_alert("warn", "missing_today_state", f"No trading-day state record for {as_of_date.isoformat()}."))

    latest_date = _as_date(latest.get("date")) if latest else None
    stale_delta = (as_of_date - latest_date).days if latest_date else None
    if stale_delta is not None and stale_delta > max(int(stale_days), 0):
        alerts.append(_alert("block", "stale_state", f"Latest trading-day state is {stale_delta} calendar days old."))

    current_status = str(current.get("status", "") or "")
    if current_status == "block":
        alerts.append(_alert("block", "current_state_block", "Current trading-day state is blocked."))
    elif current_status == "warn":
        alerts.append(_alert("warn", "current_state_warn", "Current trading-day state has warnings."))

    for phase in list(current.get("phases") or []):
        phase_status = str(phase.get("status", "") or "")
        if phase_status in {"warn", "block"}:
            alerts.append(
                _alert(
                    phase_status,
                    "current_phase_issue",
                    f"{phase.get('phase', '')} phase is {phase_status}.",
                    phase=str(phase.get("phase", "") or ""),
                )
            )

    repeated = _repeated_phase_issues(recent, threshold=max(int(repeat_threshold), 1))
    for phase, payload in repeated.items():
        severity = "block" if payload["block_count"] else "warn"
        alerts.append(
            _alert(
                severity,
                "repeated_phase_issue",
                f"{phase} phase had {payload['count']} warn/block records in the recent window.",
                phase=phase,
                count=payload["count"],
            )
        )

    status = _rollup_status([str(alert.get("severity", "pass")) for alert in alerts])
    return {
        "generated_at": datetime.now().isoformat(),
        "as_of": as_of_date.isoformat(),
        "status": status,
        "total_records": len(sorted_records),
        "latest_date": latest_date.isoformat() if latest_date else "",
        "latest_status": str(latest.get("status", "") or ""),
        "today_record_count": len(today_records),
        "stale_days": stale_delta,
        "alerts": alerts,
        "phase_issue_counts": dict(_phase_issue_counts(recent)),
        "action_items": _action_items(alerts),
    }


def render_trading_day_watchdog_markdown(report: dict[str, Any] | None) -> str:
    report = report or {}
    lines = [
        "# Trading Day Watchdog",
        "",
        f"- Status: {report.get('status', 'pass')}",
        f"- As of: {report.get('as_of', '')}",
        f"- Latest state date: {report.get('latest_date', '') or '-'}",
        f"- Latest state status: {report.get('latest_status', '') or '-'}",
        f"- Today records: {int(report.get('today_record_count', 0) or 0)}",
        f"- Total records: {int(report.get('total_records', 0) or 0)}",
        "",
        "## Alerts",
        "",
    ]
    alerts = list(report.get("alerts") or [])
    if alerts:
        for alert in alerts:
            phase = f" [{alert.get('phase')}]" if alert.get("phase") else ""
            lines.append(f"- {alert.get('severity', '')}{phase} {alert.get('name', '')}: {alert.get('message', '')}")
    else:
        lines.append("- No trading-day process alert.")
    action_items = list(report.get("action_items") or [])
    if action_items:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in action_items)
    return "\n".join(lines)


def _repeated_phase_issues(records: list[dict[str, Any]], *, threshold: int) -> dict[str, dict[str, int]]:
    counts: Counter[str] = Counter()
    block_counts: Counter[str] = Counter()
    for record in records:
        for phase in list(record.get("phases") or []):
            status = str(phase.get("status", "") or "")
            phase_name = str(phase.get("phase", "") or "")
            if not phase_name or status not in {"warn", "block"}:
                continue
            counts[phase_name] += 1
            if status == "block":
                block_counts[phase_name] += 1
    return {
        phase: {"count": count, "block_count": block_counts.get(phase, 0)}
        for phase, count in counts.items()
        if count >= threshold
    }


def _phase_issue_counts(records: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for record in records:
        for phase in list(record.get("phases") or []):
            if str(phase.get("status", "") or "") in {"warn", "block"}:
                phase_name = str(phase.get("phase", "") or "")
                if phase_name:
                    counts[phase_name] += 1
    return counts


def _action_items(alerts: list[dict[str, Any]]) -> list[str]:
    if not alerts:
        return ["Trading-day watchdog is clean; keep recording state after each workflow run."]
    names = {str(alert.get("name", "")) for alert in alerts}
    items: list[str] = []
    if "no_state_history" in names or "missing_today_state" in names:
        items.append("Run workflow trading-day with --record-state before relying on intraday decisions.")
    if "stale_state" in names:
        items.append("Refresh the trading-day workflow before adding new risk.")
    if "current_state_block" in names:
        items.append("Treat the next trading session as no-new-position until the block is cleared.")
    repeated = [alert for alert in alerts if alert.get("name") == "repeated_phase_issue"]
    if repeated:
        phases = ", ".join(sorted({str(alert.get("phase", "")) for alert in repeated if alert.get("phase")}))
        items.append(f"Repeated phase issues detected in {phases}; tighten that checklist before scaling trades.")
    if not items:
        items.append("Review warning alerts and complete the missing trading-day phase tasks.")
    return items


def _alert(severity: str, name: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"severity": severity, "name": name, "message": message}
    payload.update(extra)
    return payload


def _rollup_status(statuses: list[str]) -> str:
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _as_date(value: str | date | datetime | Any | None) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None
