from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import floor
from pathlib import Path
from typing import Any

from quant_system.storage.jsonl import append_jsonl, read_jsonl


STRUCTURE_GATE_CHECKS = {
    "entry_structure",
    "volume_price_confirmation",
    "false_breakout",
    "candle_warning",
    "chase_risk",
    "tape_reading",
    "value_filter",
}


@dataclass(frozen=True)
class ExecutionConfirmCheck:
    name: str
    status: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionConfirmation:
    created_at: str
    symbol: str
    status: str
    decision: str
    current_price: float
    reference_price: float | None
    price_deviation_pct: float | None
    requested_pct: float
    confirmed_pct: float
    requested_value: float
    confirmed_value: float
    suggested_quantity: int
    lot_size: int
    final_gate_status: str
    pretrade_status: str
    checks: list[ExecutionConfirmCheck]
    action_items: list[str]
    pretrade_result: dict
    battle_candidate: dict | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["checks"] = [check.to_dict() for check in self.checks]
        return data


def build_execution_confirmation(
    pretrade_result: Any,
    *,
    battle_plan: dict[str, Any] | None = None,
    symbol: str | None = None,
    current_price: float | None = None,
    planned_pct: float | None = None,
    cash: float | None = None,
    reference_price: float | None = None,
    warn_scale: float = 0.5,
    max_price_deviation_pct: float = 0.015,
    hard_chase_pct: float = 0.03,
    lot_size: int = 100,
) -> ExecutionConfirmation:
    pretrade = _as_dict(pretrade_result)
    normalized_symbol = str(symbol or pretrade.get("symbol", "")).zfill(6)
    current = _float(current_price if current_price is not None else pretrade.get("entry_price"))
    requested_pct = _float(planned_pct if planned_pct is not None else pretrade.get("planned_pct"))
    cash_value = _cash(cash, pretrade, requested_pct)
    battle = battle_plan or {}
    candidate = _battle_candidate(battle, normalized_symbol)
    ref_price = _reference_price(reference_price, candidate, pretrade)

    checks = [
        _check_current_price(current),
        _check_final_gate(battle),
        _check_battle_candidate(battle, candidate, normalized_symbol),
        _check_pretrade(pretrade),
        _check_pretrade_structure_evidence(pretrade),
        _check_position_budget(requested_pct, _float(pretrade.get("allowed_pct"))),
        _check_price_drift(current, ref_price, max_price_deviation_pct, hard_chase_pct),
    ]
    status = _rollup_status(checks)
    allowed_pct = _float(pretrade.get("allowed_pct"))
    confirmed_pct = _confirmed_pct(status, requested_pct, allowed_pct, warn_scale)
    suggested_quantity = _suggested_quantity(cash_value, confirmed_pct, current, lot_size)
    confirmed_value = round(suggested_quantity * current, 2)
    if status != "block" and confirmed_pct > 0 and suggested_quantity <= 0:
        checks.append(
            ExecutionConfirmCheck(
                "lot_size",
                "block",
                f"Confirmed budget is below one board lot; A-share BUY quantity must be at least {lot_size} shares.",
            )
        )
        status = _rollup_status(checks)
        confirmed_pct = 0.0
        confirmed_value = 0.0

    deviation = None if ref_price in (None, 0) else current / float(ref_price) - 1.0
    decision = _decision(status)
    action_items = _action_items(
        status=status,
        symbol=normalized_symbol,
        current_price=current,
        confirmed_pct=confirmed_pct,
        confirmed_value=confirmed_value,
        suggested_quantity=suggested_quantity,
        checks=checks,
    )
    return ExecutionConfirmation(
        created_at=datetime.now(timezone.utc).isoformat(),
        symbol=normalized_symbol,
        status=status,
        decision=decision,
        current_price=current,
        reference_price=ref_price,
        price_deviation_pct=deviation,
        requested_pct=requested_pct,
        confirmed_pct=round(confirmed_pct, 6),
        requested_value=round(cash_value * requested_pct, 2),
        confirmed_value=confirmed_value,
        suggested_quantity=suggested_quantity if status != "block" else 0,
        lot_size=lot_size,
        final_gate_status=str(battle.get("status", "") or ""),
        pretrade_status=str(pretrade.get("status", "") or ""),
        checks=checks,
        action_items=action_items,
        pretrade_result=pretrade,
        battle_candidate=candidate,
    )


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return dict(value or {})


def _cash(cash: float | None, pretrade: dict[str, Any], requested_pct: float) -> float:
    if cash is not None:
        return float(cash)
    planned_value = _float(pretrade.get("planned_value"))
    if requested_pct > 0 and planned_value > 0:
        return planned_value / requested_pct
    return 0.0


def _battle_candidate(battle_plan: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    for group in ("buy_candidates", "blocked_candidates"):
        for item in list(battle_plan.get(group, []) or []):
            if str(item.get("symbol", "")).zfill(6) == symbol:
                row = dict(item)
                row["battle_group"] = group
                return row
    return None


def _reference_price(reference_price: float | None, candidate: dict[str, Any] | None, pretrade: dict[str, Any]) -> float | None:
    if reference_price is not None:
        return float(reference_price)
    if candidate and candidate.get("entry_price") not in (None, ""):
        return _float(candidate.get("entry_price"))
    if pretrade.get("candidate_snapshot"):
        close = (pretrade.get("candidate_snapshot") or {}).get("close")
        if close not in (None, ""):
            return _float(close)
    entry = pretrade.get("entry_price")
    return _float(entry) if entry not in (None, "") else None


def _check_current_price(current_price: float) -> ExecutionConfirmCheck:
    if current_price <= 0:
        return ExecutionConfirmCheck("current_price", "block", "Current price must be greater than zero; order confirmation is blocked.")
    return ExecutionConfirmCheck("current_price", "pass", f"Current price {current_price:.2f} is available for confirmation.")


def _check_final_gate(battle_plan: dict[str, Any]) -> ExecutionConfirmCheck:
    if not battle_plan:
        return ExecutionConfirmCheck("final_gate", "warn", "No final battle plan was provided; confirmation is downgraded to single-symbol precheck.")
    status = str(battle_plan.get("status", "") or "")
    decision = str(battle_plan.get("decision", "") or "")
    if status == "block":
        return ExecutionConfirmCheck("final_gate", "block", f"Final battle plan blocks execution: {decision}")
    if status == "warn":
        return ExecutionConfirmCheck("final_gate", "warn", f"Final battle plan is in warning mode: {decision}")
    return ExecutionConfirmCheck("final_gate", "pass", f"Final battle plan passed: {decision}")


def _check_battle_candidate(battle_plan: dict[str, Any], candidate: dict[str, Any] | None, symbol: str) -> ExecutionConfirmCheck:
    if not battle_plan:
        return ExecutionConfirmCheck("battle_candidate", "warn", "No battle-plan candidate context is available for this symbol.")
    if candidate is None:
        return ExecutionConfirmCheck("battle_candidate", "warn", f"{symbol} is not present in the final battle-plan list; verify whether it was filtered out by limits.")
    if candidate.get("battle_group") == "blocked_candidates":
        return ExecutionConfirmCheck("battle_candidate", "block", f"{symbol} is in the blocked candidate list: {candidate.get('reason', '')}")
    return ExecutionConfirmCheck("battle_candidate", "pass", f"{symbol} is in the executable candidate list.")


def _check_pretrade(pretrade: dict[str, Any]) -> ExecutionConfirmCheck:
    status = str(pretrade.get("status", "") or "")
    if status == "block":
        return ExecutionConfirmCheck("pretrade", "block", "Realtime precheck still has blocking items.")
    if status == "warn":
        return ExecutionConfirmCheck("pretrade", "warn", "Realtime precheck has warning items.")
    return ExecutionConfirmCheck("pretrade", "pass", "Realtime precheck passed.")


def _check_pretrade_structure_evidence(pretrade: dict[str, Any]) -> ExecutionConfirmCheck:
    relevant = [
        check
        for check in list(pretrade.get("checks") or [])
        if str(check.get("name", "") or "") in STRUCTURE_GATE_CHECKS
        and str(check.get("status", "") or "") in {"warn", "block"}
    ]
    if not relevant:
        return ExecutionConfirmCheck("pretrade_structure", "pass", "No structure-gate warning remains in pretrade evidence.")
    status = _rollup_status(
        [
            ExecutionConfirmCheck(
                name=str(item.get("name", "") or "pretrade_structure"),
                status=str(item.get("status", "") or "warn"),
                message=str(item.get("message", "") or ""),
            )
            for item in relevant
        ]
    )
    summary = "; ".join(str(item.get("message", "") or item.get("name", "")) for item in relevant[:3])
    return ExecutionConfirmCheck("pretrade_structure", status, summary)


def _check_position_budget(requested_pct: float, allowed_pct: float) -> ExecutionConfirmCheck:
    if allowed_pct <= 0:
        return ExecutionConfirmCheck("position_budget", "block", "Allowed position is zero; confirmation is blocked.")
    if requested_pct > allowed_pct + 1e-12:
        return ExecutionConfirmCheck("position_budget", "block", f"Requested position {requested_pct:.1%} exceeds allowed cap {allowed_pct:.1%}.")
    return ExecutionConfirmCheck("position_budget", "pass", f"Requested position {requested_pct:.1%} is within allowed cap {allowed_pct:.1%}.")


def _check_price_drift(
    current_price: float,
    reference_price: float | None,
    max_price_deviation_pct: float,
    hard_chase_pct: float,
) -> ExecutionConfirmCheck:
    if reference_price in (None, 0):
        return ExecutionConfirmCheck("price_drift", "warn", "Reference price is missing; chase-risk cannot be evaluated.")
    deviation = current_price / float(reference_price) - 1.0
    if deviation > hard_chase_pct:
        return ExecutionConfirmCheck("price_drift", "block", f"Current price is {deviation:.1%} above reference, above hard chase limit {hard_chase_pct:.1%}.")
    if deviation > max_price_deviation_pct:
        return ExecutionConfirmCheck("price_drift", "warn", f"Current price is {deviation:.1%} above reference; only reduced-size confirmation is allowed.")
    if deviation < -0.08:
        return ExecutionConfirmCheck("price_drift", "warn", f"Current price is {abs(deviation):.1%} below reference; check for bad news or input errors.")
    return ExecutionConfirmCheck("price_drift", "pass", f"Current price deviation versus reference is {deviation:.1%}.")


def _confirmed_pct(status: str, requested_pct: float, allowed_pct: float, warn_scale: float) -> float:
    if status == "block":
        return 0.0
    base = max(min(requested_pct, allowed_pct), 0.0)
    if status == "warn":
        return base * max(min(warn_scale, 1.0), 0.0)
    return base


def _suggested_quantity(cash: float, confirmed_pct: float, current_price: float, lot_size: int) -> int:
    if cash <= 0 or confirmed_pct <= 0 or current_price <= 0 or lot_size <= 0:
        return 0
    raw_quantity = cash * confirmed_pct / current_price
    return int(floor(raw_quantity / lot_size) * lot_size)


def _rollup_status(checks: list[ExecutionConfirmCheck]) -> str:
    statuses = {check.status for check in checks}
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _decision(status: str) -> str:
    return {
        "pass": "PASS: execute the confirmed order, then immediately record fill price, quantity, and rationale.",
        "warn": "WARN: only execute the reduced-size confirmation; do not chase price or manually increase size.",
        "block": "BLOCK: do not place the order; clear blocking evidence and regenerate the battle plan or confirmation.",
    }[status]


def _action_items(
    *,
    status: str,
    symbol: str,
    current_price: float,
    confirmed_pct: float,
    confirmed_value: float,
    suggested_quantity: int,
    checks: list[ExecutionConfirmCheck],
) -> list[str]:
    if status == "block":
        items = [f"{symbol}: do not submit a BUY order in the trading terminal."]
    else:
        items = [
            f"{symbol}: suggested order quantity is {suggested_quantity} shares, reference value {confirmed_value:.2f}, confirmed position {confirmed_pct:.1%}.",
            f"Before submitting, re-check that the live quote is not above the confirmed price {current_price:.2f}.",
        ]
    for check in checks:
        if check.status in {"block", "warn"}:
            items.append(f"[{check.status}] {check.message}")
    if status != "block":
        items.append("After fill, immediately write the trade journal and verify it obeyed the final battle plan.")
    return items


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def append_execution_confirmation_record(
    path: Path,
    confirmation: ExecutionConfirmation | dict[str, Any],
    *,
    sqlite_path: Path | None = None,
) -> None:
    payload = confirmation.to_dict() if hasattr(confirmation, "to_dict") else dict(confirmation)
    append_jsonl(path, payload)
    if sqlite_path:
        from quant_system.storage.sqlite_store import SQLiteStore

        SQLiteStore(sqlite_path).insert_execution_confirmation(payload)


def read_execution_confirmation_records(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)
