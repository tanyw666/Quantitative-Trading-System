from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quant_system.storage.jsonl import append_jsonl, read_jsonl
from quant_system.storage.sqlite_store import SQLiteStore


def build_order_approval(
    *,
    symbol: str,
    assistant: dict[str, Any] | None = None,
    battle_plan: dict[str, Any] | None = None,
    pretrade: dict[str, Any] | None = None,
    confirmation: dict[str, Any] | None = None,
    tradability: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    assistant = assistant or {}
    battle_plan = battle_plan or {}
    pretrade = pretrade or {}
    confirmation = confirmation or {}
    tradability = tradability or {}
    status = _rollup_status(
        [
            str(assistant.get("status", "") or "pass"),
            str(battle_plan.get("status", "") or "pass"),
            str(pretrade.get("status", "") or "pass"),
            str(confirmation.get("status", "") or "pass"),
            str(tradability.get("status", "") or "pass"),
        ]
    )
    confirmed_pct = float(confirmation.get("confirmed_pct", tradability.get("planned_pct", 0)) or 0)
    confirmed_value = float(confirmation.get("confirmed_value", tradability.get("planned_value", 0)) or 0)
    suggested_quantity = int(confirmation.get("suggested_quantity", 0) or tradability.get("suggested_quantity", 0) or 0)
    return {
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "symbol": str(symbol).zfill(6),
        "status": status,
        "decision": _decision(status),
        "confirmed_pct": 0.0 if status == "block" else confirmed_pct,
        "confirmed_value": 0.0 if status == "block" else confirmed_value,
        "suggested_quantity": 0 if status == "block" else suggested_quantity,
        "evidence": {
            "assistant_status": str(assistant.get("status", "") or ""),
            "battle_plan_status": str(battle_plan.get("status", "") or ""),
            "pretrade_status": str(pretrade.get("status", "") or ""),
            "confirmation_status": str(confirmation.get("status", "") or ""),
            "tradability_status": str(tradability.get("status", "") or ""),
        },
        "reasons": _reasons(
            assistant=assistant,
            battle_plan=battle_plan,
            pretrade=pretrade,
            confirmation=confirmation,
            tradability=tradability,
        ),
        "action_items": _action_items(
            status=status,
            assistant=assistant,
            pretrade=pretrade,
            confirmation=confirmation,
            tradability=tradability,
        ),
        "assistant": assistant,
        "battle_plan": battle_plan,
        "pretrade": pretrade,
        "confirmation": confirmation,
        "tradability": tradability,
    }


def append_order_approval_record(path: Path, record: dict[str, Any], sqlite_path: Path | None = None) -> None:
    append_jsonl(path, record)
    if sqlite_path is not None:
        store = SQLiteStore(sqlite_path)
        store.init()
        store.insert_order_approval(record)


def read_order_approval_records(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    records = read_jsonl(path)
    if limit is None:
        return records
    visible_limit = max(int(limit), 0)
    return records[-visible_limit:] if visible_limit else []


def summarize_order_approvals(records: list[dict[str, Any]], *, limit: int = 20) -> dict[str, Any]:
    status_counts: Counter[str] = Counter(str(item.get("status", "") or "") for item in records)
    symbol_counts: Counter[str] = Counter(str(item.get("symbol", "") or "") for item in records)
    blocked = [item for item in records if str(item.get("status", "") or "") == "block"]
    warned = [item for item in records if str(item.get("status", "") or "") == "warn"]
    visible_limit = max(int(limit), 0)
    return {
        "total": len(records),
        "status_counts": {key: value for key, value in status_counts.items() if key},
        "block_count": len(blocked),
        "warn_count": len(warned),
        "by_symbol": {key: value for key, value in symbol_counts.items() if key},
        "latest": records[-visible_limit:] if visible_limit else [],
        "action_items": _summary_action_items(blocked, warned),
    }


def render_order_approval_markdown(record: dict[str, Any] | None) -> str:
    record = record or {}
    lines = [
        "# Order Approval",
        "",
        f"- Symbol: {record.get('symbol', '')}",
        f"- Status: {record.get('status', '')}",
        f"- Decision: {record.get('decision', '')}",
        f"- Confirmed pct: {_pct(record.get('confirmed_pct'))}",
        f"- Confirmed value: {float(record.get('confirmed_value', 0) or 0):.2f}",
        f"- Suggested quantity: {int(record.get('suggested_quantity', 0) or 0)}",
        "",
        "## Evidence",
        "",
    ]
    for key, value in dict(record.get("evidence") or {}).items():
        lines.append(f"- {key}: {value}")
    reasons = list(record.get("reasons") or [])
    if reasons:
        lines.extend(["", "## Reasons", ""])
        lines.extend(f"- {item}" for item in reasons)
    actions = list(record.get("action_items") or [])
    if actions:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in actions)
    return "\n".join(lines)


def render_order_approval_summary_markdown(summary: dict[str, Any] | None) -> str:
    summary = summary or {}
    lines = [
        "# Order Approval History",
        "",
        f"- Total: {int(summary.get('total', 0) or 0)}",
        f"- Status counts: {summary.get('status_counts', {})}",
        f"- Block count: {int(summary.get('block_count', 0) or 0)}",
        f"- Warn count: {int(summary.get('warn_count', 0) or 0)}",
        "",
        "## Latest",
        "",
    ]
    latest = list(summary.get("latest") or [])
    if latest:
        lines.extend(["| Time | Symbol | Status | Quantity | Decision |", "| --- | --- | --- | ---: | --- |"])
        for item in latest:
            lines.append(
                f"| {item.get('created_at', '')} | {item.get('symbol', '')} | {item.get('status', '')} | "
                f"{int(item.get('suggested_quantity', 0) or 0)} | {item.get('decision', '')} |"
            )
    else:
        lines.append("- No approval record.")
    actions = list(summary.get("action_items") or [])
    if actions:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in actions)
    return "\n".join(lines)


def _reasons(
    *,
    assistant: dict[str, Any],
    battle_plan: dict[str, Any],
    pretrade: dict[str, Any],
    confirmation: dict[str, Any],
    tradability: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    reasons.extend(str(item) for item in list(battle_plan.get("reasons") or [])[:5])
    for payload, prefix in [
        (assistant, "assistant"),
        (pretrade, "pretrade"),
        (confirmation, "confirmation"),
        (tradability, "tradability"),
    ]:
        status = str(payload.get("status", "") or "")
        if status in {"warn", "block"}:
            reasons.append(f"{prefix}: {status}")
    for check in list(pretrade.get("checks") or []):
        if str(check.get("status", "") or "") in {"warn", "block"}:
            reasons.append(f"pretrade.{check.get('name', '')}: {check.get('message', '')}")
    for check in list(confirmation.get("checks") or []):
        if str(check.get("status", "") or "") in {"warn", "block"}:
            reasons.append(f"confirmation.{check.get('name', '')}: {check.get('message', '')}")
    for check in list(tradability.get("checks") or []):
        if str(check.get("status", "") or "") in {"warn", "block"}:
            reasons.append(f"tradability.{check.get('name', '')}: {check.get('message', '')}")
    return _dedupe_text(reasons)


def _action_items(
    *,
    status: str,
    assistant: dict[str, Any],
    pretrade: dict[str, Any],
    confirmation: dict[str, Any],
    tradability: dict[str, Any],
) -> list[str]:
    if status == "block":
        items = ["Do not place this order. Save the approval record and clear the blocking evidence first."]
    elif status == "warn":
        items = ["Only place a reduced-size order after manually accepting every warning in the approval record."]
    else:
        items = ["Order approval passed; after fill, immediately record the trade with the approval evidence."]
    items.extend(str(item.get("text", "")) for item in list(assistant.get("urgent_actions") or []) if item.get("text"))
    items.extend(str(item) for item in list(pretrade.get("action_items") or [])[:5])
    items.extend(str(item) for item in list(confirmation.get("action_items") or [])[:5])
    items.extend(str(item) for item in list(tradability.get("action_items") or [])[:5])
    return _dedupe_text(items)


def _summary_action_items(blocked: list[dict[str, Any]], warned: list[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    if blocked:
        items.append("Blocked approvals exist; do not treat those symbols as tradable until a clean approval is generated.")
    if warned:
        items.append("Warn approvals exist; compare later fills against reduced-size approval quantities.")
    if not items:
        items.append("Approval history is clean in the current sample.")
    return items


def _rollup_status(statuses: list[str]) -> str:
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _decision(status: str) -> str:
    if status == "block":
        return "BLOCK: do not place this order."
    if status == "warn":
        return "WARN: only continue with reduced size after manual acceptance."
    return "PASS: approved for manual order entry."


def _dedupe_text(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _pct(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.1%}"
