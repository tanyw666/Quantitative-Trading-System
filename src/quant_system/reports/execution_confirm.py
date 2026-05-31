from __future__ import annotations

from typing import Any


def render_execution_confirmation_markdown(result: Any) -> str:
    data = result.to_dict() if hasattr(result, "to_dict") else dict(result or {})
    lines = [
        f"# Intraday Execution Confirmation {data.get('symbol', '')}",
        "",
        f"- Status: {data.get('status', '')}",
        f"- Decision: {data.get('decision', '')}",
        f"- Current price: {float(data.get('current_price', 0) or 0):.2f}",
        f"- Reference price: {_price(data.get('reference_price'))}",
        f"- Price deviation: {_pct(data.get('price_deviation_pct'))}",
        f"- Requested position: {float(data.get('requested_pct', 0) or 0):.1%}",
        f"- Confirmed position: {float(data.get('confirmed_pct', 0) or 0):.1%}",
        f"- Requested value: {float(data.get('requested_value', 0) or 0):.2f}",
        f"- Confirmed value: {float(data.get('confirmed_value', 0) or 0):.2f}",
        f"- Suggested quantity: {int(data.get('suggested_quantity', 0) or 0)} shares",
        f"- Final gate: {data.get('final_gate_status', '')}",
        f"- Single-symbol precheck: {data.get('pretrade_status', '')}",
    ]

    battle_candidate = data.get("battle_candidate") or {}
    if battle_candidate:
        lines.extend(["", "## Battle Plan Position", ""])
        lines.append(f"- List group: {battle_candidate.get('battle_group', '')}")
        lines.append(f"- Planned position: {float(battle_candidate.get('planned_pct', 0) or 0):.1%}")
        lines.append(f"- Allowed position: {float(battle_candidate.get('allowed_pct', 0) or 0):.1%}")
        if battle_candidate.get("reason"):
            lines.append(f"- Block reason: {battle_candidate.get('reason', '')}")

    lines.extend(["", "## Checks", "", "| Item | Status | Message |", "| --- | --- | --- |"])
    for check in data.get("checks", []) or []:
        lines.append(f"| {check.get('name', '')} | {check.get('status', '')} | {check.get('message', '')} |")

    lines.extend(["", "## Action Items", ""])
    for item in data.get("action_items", []) or []:
        lines.append(f"- {item}")

    pretrade = data.get("pretrade_result") or {}
    if pretrade:
        lines.extend(["", "## Precheck Summary", ""])
        lines.append(f"- Status: {pretrade.get('status', '')}")
        lines.append(f"- Entry price: {float(pretrade.get('entry_price', 0) or 0):.2f}")
        lines.append(f"- Stop price: {_price(pretrade.get('stop_price'))}")
        lines.append(f"- Target price: {_price(pretrade.get('target_price'))}")
        reward_risk = pretrade.get("reward_risk")
        if reward_risk not in (None, ""):
            lines.append(f"- Reward/risk: {float(reward_risk):.2f}")
    return "\n".join(lines)


def _price(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.2f}"


def _pct(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.1%}"
