from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from quant_system.storage.jsonl import append_jsonl, read_jsonl
from quant_system.storage.sqlite_store import SQLiteStore


def apply_trading_day_template(timeline: dict[str, Any], phase_templates: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if not phase_templates:
        return timeline
    updated = dict(timeline)
    phases = []
    for phase in list(timeline.get("phases") or []):
        item = dict(phase)
        template = dict(phase_templates.get(str(item.get("phase", "")), {}) or {})
        if template:
            for key in ("title", "due", "next_step"):
                if template.get(key) is not None:
                    item[key] = str(template.get(key, ""))
            if template.get("checklist") is not None:
                item["checklist"] = _string_list(template.get("checklist"))
            extra_checklist = _string_list(template.get("extra_checklist"))
            if extra_checklist:
                item["checklist"] = list(item.get("checklist") or []) + extra_checklist
            extra_missing = _string_list(template.get("extra_missing"))
            if extra_missing:
                item["missing"] = list(item.get("missing") or []) + extra_missing
                item["status"] = _escalate(str(item.get("status", "") or "pass"), str(template.get("extra_missing_status", "warn") or "warn"))
        phases.append(item)
    updated["phases"] = phases
    updated["status"] = _rollup_status([str(phase.get("status", "") or "pass") for phase in phases])
    updated["action_items"] = _timeline_action_items(phases)
    return updated


def build_trading_day_state(
    timeline: dict[str, Any],
    *,
    trading_date: str = "",
    source: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    created_at = created_at or str(timeline.get("generated_at") or datetime.now().isoformat())
    state_date = trading_date or _date_from_timestamp(created_at)
    phases = []
    counts: Counter[str] = Counter()
    for raw in list(timeline.get("phases") or []):
        phase = dict(raw)
        status = str(phase.get("status", "") or "pass")
        missing = _string_list(phase.get("missing"))
        checklist = _string_list(phase.get("checklist"))
        counts[status] += 1
        phases.append(
            {
                "phase": str(phase.get("phase", "")),
                "title": str(phase.get("title", "")),
                "status": status,
                "completed": status == "pass" and not missing,
                "due": str(phase.get("due", "")),
                "missing": missing,
                "checklist": checklist,
                "next_step": str(phase.get("next_step", "")),
            }
        )
    action_items = _string_list(timeline.get("action_items"))
    return {
        "created_at": created_at,
        "date": state_date,
        "source": source,
        "status": str(timeline.get("status", "") or _rollup_status(list(counts.elements()))),
        "phase_count": len(phases),
        "pass_count": counts.get("pass", 0),
        "warn_count": counts.get("warn", 0),
        "block_count": counts.get("block", 0),
        "action_item_count": len(action_items),
        "phases": phases,
        "action_items": action_items,
    }


def append_trading_day_state_record(path: Path, record: dict[str, Any], sqlite_path: Path | None = None) -> None:
    append_jsonl(path, record)
    if sqlite_path is not None:
        store = SQLiteStore(sqlite_path)
        store.init()
        store.insert_trading_day_state(record)


def read_trading_day_state_records(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    records = read_jsonl(path)
    if limit is None:
        return records
    visible_limit = max(int(limit), 0)
    return records[-visible_limit:] if visible_limit else records


def summarize_trading_day_state_records(records: list[dict[str, Any]], *, limit: int = 20) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    phase_status_counts: Counter[str] = Counter()
    phase_problem_counts: Counter[str] = Counter()
    action_items: list[str] = []
    for record in records:
        status = str(record.get("status", "") or "")
        if status:
            status_counts[status] += 1
        for phase in list(record.get("phases") or []):
            phase_key = str(phase.get("phase", "") or "")
            phase_status = str(phase.get("status", "") or "")
            if phase_key and phase_status:
                phase_status_counts[f"{phase_key}:{phase_status}"] += 1
            if phase_key and phase_status in {"warn", "block"}:
                phase_problem_counts[phase_key] += 1
        action_items.extend(_string_list(record.get("action_items"))[:3])
    visible_limit = max(int(limit), 0)
    latest = records[-visible_limit:] if visible_limit else records
    return {
        "total_records": len(records),
        "status_counts": dict(status_counts),
        "phase_status_counts": dict(phase_status_counts),
        "phase_problem_counts": dict(phase_problem_counts),
        "latest_records": latest,
        "action_items": _summary_action_items(status_counts, phase_problem_counts, action_items),
    }


def render_trading_day_state_history_markdown(summary: dict[str, Any] | None) -> str:
    summary = summary or {}
    lines = [
        "# Trading Day State History",
        "",
        f"- total_records: {int(summary.get('total_records', 0) or 0)}",
        f"- status_counts: {summary.get('status_counts', {})}",
        f"- phase_problem_counts: {summary.get('phase_problem_counts', {})}",
    ]
    latest = list(summary.get("latest_records") or [])
    if latest:
        lines.extend(["", "| Date | Status | Pass | Warn | Block | Actions |", "| --- | --- | ---: | ---: | ---: | ---: |"])
        for record in latest:
            lines.append(
                f"| {record.get('date', '')} | {record.get('status', '')} | "
                f"{int(record.get('pass_count', 0) or 0)} | {int(record.get('warn_count', 0) or 0)} | "
                f"{int(record.get('block_count', 0) or 0)} | {int(record.get('action_item_count', 0) or 0)} |"
            )
    actions = list(summary.get("action_items") or [])
    if actions:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in actions)
    return "\n".join(lines)


def _summary_action_items(status_counts: Counter[str], phase_problem_counts: Counter[str], samples: list[str]) -> list[str]:
    items: list[str] = []
    if status_counts.get("block", 0):
        items.append("Recent trading-day states contain block records; review them before allowing new positions.")
    if status_counts.get("warn", 0):
        items.append("Warnings are still appearing in the daily process; inspect the most frequent phase problem.")
    if phase_problem_counts:
        top_phase = sorted(phase_problem_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
        items.append(f"Most repeated phase issue: {top_phase}.")
    for sample in samples[:3]:
        if sample and sample not in items:
            items.append(sample)
    if not items:
        items.append("Trading-day process history is clean in the current sample.")
    return items


def _timeline_action_items(phases: list[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for phase in phases:
        if str(phase.get("status", "") or "") in {"warn", "block"}:
            items.append(f"{phase.get('title', phase.get('phase', ''))}: {phase.get('next_step', '')}")
        for missing in _string_list(phase.get("missing")):
            items.append(missing)
    if not items:
        items.append("Trading-day process is clean; continue following each phase.")
    return items


def _date_from_timestamp(value: str) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return str(value)[:10]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        return [value] if value else []
    return [str(value)]


def _rollup_status(statuses: list[str]) -> str:
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _escalate(current: str, target: str) -> str:
    rank = {"pass": 0, "warn": 1, "block": 2}
    return target if rank.get(target, 0) > rank.get(current, 0) else current
