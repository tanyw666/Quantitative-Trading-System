from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from math import floor
from math import isfinite
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class TradabilityCheck:
    name: str
    status: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TradabilityResult:
    symbol: str
    status: str
    decision: str
    current_price: float
    latest_bar_date: str
    stale_days: int | None
    last_close: float | None
    price_vs_close_pct: float | None
    planned_pct: float
    planned_value: float
    suggested_quantity: int
    checks: list[TradabilityCheck]
    action_items: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = [check.to_dict() for check in self.checks]
        return data


def build_tradability_check(
    frame: pd.DataFrame,
    *,
    symbol: str,
    current_price: float,
    planned_pct: float,
    cash: float,
    pretrade_result: dict[str, Any] | Any | None = None,
    confirmation: dict[str, Any] | Any | None = None,
    battle_plan: dict[str, Any] | None = None,
    as_of: str | date | datetime | None = None,
    max_stale_days: int = 1,
    limit_pct: float = 0.10,
    infer_limit_pct: bool = True,
    limit_buffer_pct: float = 0.002,
    lot_size: int = 100,
) -> TradabilityResult:
    normalized_symbol = str(symbol).zfill(6)
    pretrade = _as_dict(pretrade_result)
    confirmation_payload = _as_dict(confirmation)
    latest = _latest_bar(frame, normalized_symbol)
    as_of_date = _as_date(as_of) or date.today()
    latest_date = _as_date(latest.get("date")) if latest else None
    stale_days = (as_of_date - latest_date).days if latest_date else None
    last_close = _float_or_none(latest.get("close")) if latest else None
    current = _safe_float(current_price)
    plan_pct = _safe_float(planned_pct)
    cash_value = _safe_float(cash)
    effective_limit_pct = _infer_limit_pct(latest, normalized_symbol, limit_pct) if infer_limit_pct else limit_pct
    price_vs_close = current / last_close - 1.0 if _is_positive(current) and _is_positive(last_close) else None
    planned_value = cash_value * plan_pct if _is_finite(cash_value) and _is_finite(plan_pct) else 0.0
    suggested_quantity = _suggested_quantity(cash_value, plan_pct, current, lot_size)

    checks = [
        _check_symbol_data(latest, normalized_symbol),
        _check_staleness(stale_days, max_stale_days),
        _check_current_price(current),
        _check_latest_bar_sanity(latest),
        _check_price_vs_close(price_vs_close),
        _check_limit_state(current, last_close, effective_limit_pct, limit_buffer_pct),
        _check_pretrade(pretrade),
        _check_confirmation(confirmation_payload),
        _check_battle_plan(battle_plan or {}, normalized_symbol),
        _check_cash_and_lot(cash_value, planned_value, suggested_quantity, lot_size),
        _check_position_budget(pretrade, plan_pct),
    ]
    status = _rollup_status(checks)
    return TradabilityResult(
        symbol=normalized_symbol,
        status=status,
        decision=_decision(status),
        current_price=float(current) if _is_finite(current) else 0.0,
        latest_bar_date=latest_date.isoformat() if latest_date else "",
        stale_days=stale_days,
        last_close=last_close,
        price_vs_close_pct=price_vs_close,
        planned_pct=float(plan_pct) if _is_finite(plan_pct) else 0.0,
        planned_value=round(planned_value, 2),
        suggested_quantity=suggested_quantity if status != "block" else 0,
        checks=checks,
        action_items=_action_items(status, checks),
    )


def render_tradability_markdown(result: TradabilityResult | dict[str, Any] | None) -> str:
    payload = result.to_dict() if hasattr(result, "to_dict") else dict(result or {})
    lines = [
        "# Tradability Check",
        "",
        f"- Symbol: {payload.get('symbol', '')}",
        f"- Status: {payload.get('status', '')}",
        f"- Decision: {payload.get('decision', '')}",
        f"- Current price: {float(payload.get('current_price', 0) or 0):.2f}",
        f"- Latest bar date: {payload.get('latest_bar_date', '') or '-'}",
        f"- Stale days: {payload.get('stale_days') if payload.get('stale_days') is not None else '-'}",
        f"- Last close: {_price(payload.get('last_close'))}",
        f"- Price vs close: {_pct(payload.get('price_vs_close_pct'))}",
        f"- Suggested quantity: {int(payload.get('suggested_quantity', 0) or 0)}",
        "",
        "## Checks",
        "",
    ]
    for check in list(payload.get("checks") or []):
        lines.append(f"- [{check.get('status', '')}] {check.get('name', '')}: {check.get('message', '')}")
    actions = list(payload.get("action_items") or [])
    if actions:
        lines.extend(["", "## Action Items", ""])
        lines.extend(f"- {item}" for item in actions)
    return "\n".join(lines)


def _latest_bar(frame: pd.DataFrame, symbol: str) -> dict[str, Any]:
    if frame.empty or "symbol" not in frame.columns:
        return {}
    data = frame.copy()
    data["symbol"] = data["symbol"].astype(str).str.zfill(6)
    matched = data[data["symbol"] == symbol].copy()
    if matched.empty or "date" not in matched.columns:
        return {}
    matched["date"] = pd.to_datetime(matched["date"], errors="coerce")
    matched = matched.dropna(subset=["date"])
    if matched.empty:
        return {}
    return matched.sort_values("date").iloc[-1].to_dict()


def _check_symbol_data(latest: dict[str, Any], symbol: str) -> TradabilityCheck:
    if not latest:
        return TradabilityCheck("symbol_data", "block", f"{symbol} has no OHLCV row in the current dataset.")
    return TradabilityCheck("symbol_data", "pass", f"{symbol} has latest OHLCV data.")


def _check_staleness(stale_days: int | None, max_stale_days: int) -> TradabilityCheck:
    if stale_days is None:
        return TradabilityCheck("data_staleness", "block", "Cannot determine latest bar date.")
    if stale_days < 0:
        return TradabilityCheck("data_staleness", "warn", "Latest bar date is newer than the reference date; check as-of input.")
    if stale_days > max_stale_days:
        return TradabilityCheck("data_staleness", "block", f"Latest bar is {stale_days} calendar days old; max allowed is {max_stale_days}.")
    return TradabilityCheck("data_staleness", "pass", f"Latest bar is within {max_stale_days} calendar day(s).")


def _check_current_price(current_price: float) -> TradabilityCheck:
    if not _is_positive(current_price):
        return TradabilityCheck("current_price", "block", "Current price must be a finite number greater than 0.")
    return TradabilityCheck("current_price", "pass", "Current price is positive.")


def _check_latest_bar_sanity(latest: dict[str, Any]) -> TradabilityCheck:
    if not latest:
        return TradabilityCheck("bar_sanity", "block", "No latest bar to validate.")
    open_ = _float_or_none(latest.get("open"))
    high = _float_or_none(latest.get("high"))
    low = _float_or_none(latest.get("low"))
    close = _float_or_none(latest.get("close"))
    volume = _float_or_none(latest.get("volume"))
    if None in {open_, high, low, close, volume}:
        return TradabilityCheck("bar_sanity", "block", "Latest bar has missing OHLCV fields.")
    if not all(_is_finite(value) for value in (open_, high, low, close, volume)):
        return TradabilityCheck("bar_sanity", "block", "Latest bar has non-finite OHLCV values.")
    if high < low or high < max(open_, close) or low > min(open_, close) or min(open_, high, low, close) <= 0 or volume < 0:
        return TradabilityCheck("bar_sanity", "block", "Latest bar has invalid OHLCV values.")
    if volume == 0:
        return TradabilityCheck("bar_sanity", "block", "Latest bar volume is 0; symbol may be halted or not practically tradable.")
    return TradabilityCheck("bar_sanity", "pass", "Latest bar passes basic sanity checks.")


def _check_price_vs_close(price_vs_close: float | None) -> TradabilityCheck:
    if price_vs_close is None:
        return TradabilityCheck("price_vs_close", "warn", "Cannot compare current price with latest close.")
    if price_vs_close > 0.05:
        return TradabilityCheck("price_vs_close", "warn", f"Current price is {price_vs_close:.1%} above latest close; chase risk is elevated.")
    if price_vs_close < -0.08:
        return TradabilityCheck("price_vs_close", "warn", f"Current price is {abs(price_vs_close):.1%} below latest close; check for fresh bad news or bad input.")
    return TradabilityCheck("price_vs_close", "pass", f"Current price deviates {price_vs_close:.1%} from latest close.")


def _check_limit_state(
    current_price: float,
    last_close: float | None,
    limit_pct: float,
    limit_buffer_pct: float,
) -> TradabilityCheck:
    if not _is_positive(current_price):
        return TradabilityCheck("limit_state", "block", "Cannot estimate limit state because current price is invalid.")
    if not _is_positive(last_close):
        return TradabilityCheck("limit_state", "warn", "Cannot estimate limit-up/limit-down state without latest close.")
    up = last_close * (1 + limit_pct)
    down = last_close * (1 - limit_pct)
    if current_price >= up * (1 - limit_buffer_pct):
        return TradabilityCheck("limit_state", "block", f"Current price is near estimated {limit_pct:.0%} limit-up {up:.2f}; do not chase buy.")
    if current_price <= down * (1 + limit_buffer_pct):
        return TradabilityCheck("limit_state", "block", f"Current price is near estimated {limit_pct:.0%} limit-down {down:.2f}; liquidity risk blocks trading.")
    return TradabilityCheck("limit_state", "pass", f"Current price is not near estimated {limit_pct:.0%} limit bands.")


def _check_pretrade(pretrade: dict[str, Any]) -> TradabilityCheck:
    if not pretrade:
        return TradabilityCheck("pretrade", "warn", "No pretrade result was supplied.")
    status = str(pretrade.get("status", "") or "")
    if status == "block":
        return TradabilityCheck("pretrade", "block", "Pretrade gate is blocked.")
    if status == "warn":
        return TradabilityCheck("pretrade", "warn", "Pretrade gate has warnings.")
    return TradabilityCheck("pretrade", "pass", "Pretrade gate passed.")


def _check_confirmation(confirmation: dict[str, Any]) -> TradabilityCheck:
    if not confirmation:
        return TradabilityCheck("execution_confirmation", "warn", "No execution confirmation was supplied.")
    status = str(confirmation.get("status", "") or "")
    if status == "block":
        return TradabilityCheck("execution_confirmation", "block", "Execution confirmation is blocked.")
    if status == "warn":
        return TradabilityCheck("execution_confirmation", "warn", "Execution confirmation requires reduced size.")
    return TradabilityCheck("execution_confirmation", "pass", "Execution confirmation passed.")


def _check_battle_plan(battle_plan: dict[str, Any], symbol: str) -> TradabilityCheck:
    if not battle_plan:
        return TradabilityCheck("final_battle_plan", "warn", "No final battle plan was supplied.")
    status = str(battle_plan.get("status", "") or "")
    if status == "block":
        return TradabilityCheck("final_battle_plan", "block", "Final battle plan blocks new buys.")
    blocked = [item for item in list(battle_plan.get("blocked_candidates") or []) if str(item.get("symbol", "")).zfill(6) == symbol]
    if blocked:
        return TradabilityCheck("final_battle_plan", "block", f"{symbol} appears in final battle plan blocked candidates.")
    if status == "warn":
        return TradabilityCheck("final_battle_plan", "warn", "Final battle plan is in warn mode.")
    return TradabilityCheck("final_battle_plan", "pass", "Final battle plan does not block this symbol.")


def _check_cash_and_lot(cash: float, planned_value: float, quantity: int, lot_size: int) -> TradabilityCheck:
    if not _is_positive(cash):
        return TradabilityCheck("cash_lot", "block", "Cash must be a finite number greater than 0.")
    if not _is_finite(planned_value):
        return TradabilityCheck("cash_lot", "block", "Planned value must be finite.")
    if planned_value > cash + 1e-9:
        return TradabilityCheck("cash_lot", "block", "Planned value is greater than available cash.")
    if quantity < lot_size:
        return TradabilityCheck("cash_lot", "block", f"Planned order is smaller than one lot ({lot_size} shares).")
    return TradabilityCheck("cash_lot", "pass", f"Cash and lot-size constraints allow {quantity} shares.")


def _check_position_budget(pretrade: dict[str, Any], planned_pct: float) -> TradabilityCheck:
    if not pretrade:
        return TradabilityCheck("position_budget", "warn", "Cannot verify planned percent without pretrade result.")
    allowed = _float_or_none(pretrade.get("allowed_pct"))
    if allowed is None:
        return TradabilityCheck("position_budget", "warn", "Pretrade result has no allowed_pct.")
    if not _is_finite(planned_pct) or planned_pct < 0:
        return TradabilityCheck("position_budget", "block", "Planned pct must be a finite non-negative number.")
    if allowed < 0:
        return TradabilityCheck("position_budget", "block", "Allowed pct from pretrade must be non-negative.")
    if planned_pct > allowed + 1e-12:
        return TradabilityCheck("position_budget", "block", f"Planned pct {planned_pct:.1%} exceeds allowed pct {allowed:.1%}.")
    return TradabilityCheck("position_budget", "pass", f"Planned pct {planned_pct:.1%} is within allowed pct {allowed:.1%}.")


def _suggested_quantity(cash: float, planned_pct: float, current_price: float, lot_size: int) -> int:
    if not all(_is_finite(value) for value in (cash, planned_pct, current_price)) or cash <= 0 or planned_pct <= 0 or current_price <= 0 or lot_size <= 0:
        return 0
    raw = cash * planned_pct / current_price
    return int(floor(raw / lot_size) * lot_size)


def _infer_limit_pct(latest: dict[str, Any], symbol: str, fallback: float) -> float:
    name = str((latest or {}).get("name", "") or "").upper()
    if "ST" in name:
        return 0.05
    if symbol.startswith(("688", "689", "300", "301")):
        return 0.20
    if symbol.startswith(("8", "4", "920")):
        return 0.30
    return fallback


def _action_items(status: str, checks: list[TradabilityCheck]) -> list[str]:
    if status == "block":
        items = ["Do not place the order; clear block checks and rerun portfolio tradable."]
    elif status == "warn":
        items = ["Only continue after manually accepting every warning and reducing size if needed."]
    else:
        items = ["Tradability checks are clean; still record execution confirmation and final trade log after fill."]
    items.extend(f"[{check.status}] {check.message}" for check in checks if check.status in {"warn", "block"})
    return items


def _decision(status: str) -> str:
    if status == "block":
        return "Not tradable now."
    if status == "warn":
        return "Tradable only with manual warning acceptance and reduced risk."
    return "Tradable under the current checks."


def _rollup_status(checks: list[TradabilityCheck]) -> str:
    statuses = {check.status for check in checks}
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return dict(value)


def _as_date(value: str | date | datetime | Any | None) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, "") or pd.isna(value):
        return None
    result = float(value)
    return result if _is_finite(result) else None


def _safe_float(value: Any) -> float:
    try:
        if value in (None, "") or pd.isna(value):
            return float("nan")
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _is_finite(value: Any) -> bool:
    try:
        return isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _is_positive(value: Any) -> bool:
    return _is_finite(value) and float(value) > 0


def _pct(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.1%}"


def _price(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{float(value):.2f}"
