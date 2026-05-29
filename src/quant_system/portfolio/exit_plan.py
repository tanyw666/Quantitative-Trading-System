from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from math import floor
from pathlib import Path
from typing import Any

from quant_system.portfolio.positions import PositionBook
from quant_system.portfolio.lots import build_lot_book
from quant_system.storage.jsonl import append_jsonl, read_jsonl


@dataclass(frozen=True)
class ExitPlanItem:
    symbol: str
    name: str
    plan_type: str
    action: str
    status: str
    priority: int
    reason: str
    current_quantity: int
    sell_quantity: int
    target_quantity: int
    market_price: float | None = None
    avg_cost: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    unrealized_return: float | None = None
    exposure_pct: float | None = None
    holding_days: int | None = None
    expected_cash_release: float | None = None
    lot_id: str = ""
    entry_date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExitPlan:
    created_at: str
    plan_date: str
    status: str
    total_positions: int
    sell_all_count: int
    take_profit_count: int
    reduce_count: int
    time_stop_count: int
    invalidated_count: int
    watch_count: int
    hold_count: int
    total_sell_quantity: int
    expected_cash_release: float
    items: list[ExitPlanItem]
    action_items: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["items"] = [item.to_dict() for item in self.items]
        return data


def build_exit_plan(
    book: PositionBook,
    *,
    trade_records: list[dict[str, Any]] | None = None,
    stops: dict[str, float] | None = None,
    targets: dict[str, float] | None = None,
    invalidated: dict[str, str] | None = None,
    max_position_pct: float = 0.2,
    max_holding_days: int = 20,
    time_stop_min_return_pct: float = 0.0,
    profit_take_pct: float = 0.5,
    plan_date: str | None = None,
) -> ExitPlan:
    stops = _normalize_price_map(stops)
    targets = _normalize_price_map(targets)
    invalidated = {str(key).zfill(6): str(value or "strategy invalidated") for key, value in (invalidated or {}).items()}
    entry_dates = latest_entry_dates(trade_records or [])
    current_date = _parse_date(plan_date) or date.today()
    items = [
        _build_exit_item(
            position,
            stop_price=stops.get(position.symbol),
            target_price=targets.get(position.symbol),
            invalidated_reason=invalidated.get(position.symbol),
            entry_date=entry_dates.get(position.symbol),
            current_date=current_date,
            max_position_pct=max_position_pct,
            max_holding_days=max_holding_days,
            time_stop_min_return_pct=time_stop_min_return_pct,
            profit_take_pct=profit_take_pct,
        )
        for position in book.positions
    ]
    items = sorted(items, key=lambda item: (-item.priority, item.symbol))
    status = _rollup_status(items)
    sell_all_count = sum(1 for item in items if item.action == "sell_all")
    take_profit_count = sum(1 for item in items if item.plan_type == "take_profit")
    reduce_count = sum(1 for item in items if item.plan_type == "reduce")
    time_stop_count = sum(1 for item in items if item.plan_type == "time_stop")
    invalidated_count = sum(1 for item in items if item.plan_type == "strategy_invalidated")
    watch_count = sum(1 for item in items if item.action == "watch")
    hold_count = sum(1 for item in items if item.action == "hold")
    total_sell_quantity = sum(max(item.sell_quantity, 0) for item in items)
    expected_cash_release = round(sum(float(item.expected_cash_release or 0.0) for item in items), 2)
    return ExitPlan(
        created_at=datetime.now(timezone.utc).isoformat(),
        plan_date=current_date.isoformat(),
        status=status,
        total_positions=len(items),
        sell_all_count=sell_all_count,
        take_profit_count=take_profit_count,
        reduce_count=reduce_count,
        time_stop_count=time_stop_count,
        invalidated_count=invalidated_count,
        watch_count=watch_count,
        hold_count=hold_count,
        total_sell_quantity=total_sell_quantity,
        expected_cash_release=expected_cash_release,
        items=items,
        action_items=_action_items(items, status, expected_cash_release),
    )


def build_lot_exit_plan(
    lot_book: dict[str, Any],
    *,
    stops: dict[str, float] | None = None,
    targets: dict[str, float] | None = None,
    invalidated: dict[str, str] | None = None,
    max_holding_days: int = 20,
    time_stop_min_return_pct: float = 0.0,
    profit_take_pct: float = 0.5,
    plan_date: str | None = None,
) -> ExitPlan:
    stops = _normalize_price_map(stops)
    targets = _normalize_price_map(targets)
    invalidated = {str(key).zfill(6): str(value or "strategy invalidated") for key, value in (invalidated or {}).items()}
    current_date = _parse_date(plan_date) or date.today()
    items = [
        _build_lot_exit_item(
            lot,
            stop_price=stops.get(str(lot.get("symbol", "") or "").zfill(6)),
            target_price=targets.get(str(lot.get("symbol", "") or "").zfill(6)),
            invalidated_reason=invalidated.get(str(lot.get("symbol", "") or "").zfill(6)),
            current_date=current_date,
            max_holding_days=max_holding_days,
            time_stop_min_return_pct=time_stop_min_return_pct,
            profit_take_pct=profit_take_pct,
        )
        for lot in list((lot_book or {}).get("open_lots", []) or [])
    ]
    items = sorted(items, key=lambda item: (-item.priority, item.symbol, item.entry_date, item.lot_id))
    status = _rollup_status(items)
    sell_all_count = sum(1 for item in items if item.action == "sell_all")
    take_profit_count = sum(1 for item in items if item.plan_type == "take_profit")
    reduce_count = sum(1 for item in items if item.plan_type == "reduce")
    time_stop_count = sum(1 for item in items if item.plan_type == "time_stop")
    invalidated_count = sum(1 for item in items if item.plan_type == "strategy_invalidated")
    watch_count = sum(1 for item in items if item.action == "watch")
    hold_count = sum(1 for item in items if item.action == "hold")
    total_sell_quantity = sum(max(item.sell_quantity, 0) for item in items)
    expected_cash_release = round(sum(float(item.expected_cash_release or 0.0) for item in items), 2)
    return ExitPlan(
        created_at=datetime.now(timezone.utc).isoformat(),
        plan_date=current_date.isoformat(),
        status=status,
        total_positions=len(items),
        sell_all_count=sell_all_count,
        take_profit_count=take_profit_count,
        reduce_count=reduce_count,
        time_stop_count=time_stop_count,
        invalidated_count=invalidated_count,
        watch_count=watch_count,
        hold_count=hold_count,
        total_sell_quantity=total_sell_quantity,
        expected_cash_release=expected_cash_release,
        items=items,
        action_items=_action_items(items, status, expected_cash_release),
    )


def latest_entry_dates(trade_records: list[dict[str, Any]]) -> dict[str, date]:
    open_quantity: dict[str, int] = {}
    entry_dates: dict[str, date] = {}
    ordered = sorted(trade_records, key=lambda item: str(item.get("date", item.get("trade_date", "")) or ""))
    for record in ordered:
        symbol = str(record.get("symbol", "") or "").zfill(6)
        if not symbol:
            continue
        trade_date = _parse_date(str(record.get("date", record.get("trade_date", "")) or "")[:10])
        if trade_date is None:
            continue
        quantity = int(record.get("quantity", 0) or 0)
        side = str(record.get("side", "") or "").upper()
        if side == "BUY":
            if open_quantity.get(symbol, 0) <= 0:
                entry_dates[symbol] = trade_date
            open_quantity[symbol] = open_quantity.get(symbol, 0) + quantity
        elif side == "SELL":
            open_quantity[symbol] = max(open_quantity.get(symbol, 0) - quantity, 0)
            if open_quantity[symbol] == 0:
                entry_dates.pop(symbol, None)
    return entry_dates


def render_exit_plan_lines(plan: dict[str, Any] | ExitPlan | None) -> list[str]:
    payload = plan.to_dict() if isinstance(plan, ExitPlan) else (plan or {})
    if not payload:
        return ["- No exit plan available."]
    items = list(payload.get("items", []) or [])
    if not items:
        return ["- No open positions need an exit plan."]
    lines = [
        f"- Status: {payload.get('status', '')}",
        f"- Sell all / take profit / reduce / time stop: {int(payload.get('sell_all_count', 0) or 0)} / {int(payload.get('take_profit_count', 0) or 0)} / {int(payload.get('reduce_count', 0) or 0)} / {int(payload.get('time_stop_count', 0) or 0)}",
        f"- Expected cash release: {float(payload.get('expected_cash_release', 0) or 0):.2f}",
        "",
        "| Symbol | Lot | Type | Action | Status | Qty | Sell | Reason |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in items:
        lines.append(
            f"| {item.get('symbol', '')} | {item.get('lot_id', '')} | {item.get('plan_type', '')} | {item.get('action', '')} | "
            f"{item.get('status', '')} | {int(item.get('current_quantity', 0) or 0)} | "
            f"{int(item.get('sell_quantity', 0) or 0)} | {item.get('reason', '')} |"
        )
    action_items = list(payload.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "Action items:"])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def render_exit_plan_markdown(plan: dict[str, Any] | ExitPlan | None) -> str:
    return "\n".join(["# Exit Plan", "", *render_exit_plan_lines(plan), ""])


def append_exit_plan_record(path: Path, plan: ExitPlan | dict[str, Any]) -> None:
    payload = plan.to_dict() if isinstance(plan, ExitPlan) else dict(plan)
    append_jsonl(path, payload)


def read_exit_plan_records(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def summarize_exit_execution(
    exit_plan_records: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    *,
    lookahead_days: int = 3,
    limit: int = 20,
) -> dict[str, Any]:
    audits = _audit_exit_records(exit_plan_records, trade_records, lookahead_days=max(int(lookahead_days), 0))
    actionable = [item for item in audits if item["required_quantity"] > 0]
    executed = [item for item in actionable if item["execution_status"] == "executed"]
    partial = [item for item in actionable if item["execution_status"] == "partial"]
    missed = [item for item in actionable if item["execution_status"] == "missed"]
    delays = [float(item["delay_days"]) for item in actionable if item.get("delay_days") is not None]
    deviations = [float(item["price_deviation_pct"]) for item in actionable if item.get("price_deviation_pct") is not None]
    visible_limit = max(int(limit), 0)
    return {
        "total_items": len(audits),
        "actionable_count": len(actionable),
        "executed_count": len(executed),
        "partial_count": len(partial),
        "missed_count": len(missed),
        "execution_rate": len(executed) / len(actionable) if actionable else 0.0,
        "avg_delay_days": sum(delays) / len(delays) if delays else 0.0,
        "avg_price_deviation_pct": sum(deviations) / len(deviations) if deviations else 0.0,
        "records": audits[-visible_limit:] if visible_limit else audits,
        "action_items": _execution_action_items(len(actionable), len(executed), len(partial), len(missed), deviations),
    }


def render_exit_execution_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("actionable_count", 0) or 0) == 0:
        return ["- No actionable exit plans have been recorded yet."]
    lines = [
        f"- Actionable exits: {int(summary.get('actionable_count', 0) or 0)}",
        f"- Executed / partial / missed: {int(summary.get('executed_count', 0) or 0)} / {int(summary.get('partial_count', 0) or 0)} / {int(summary.get('missed_count', 0) or 0)}",
        f"- Execution rate: {float(summary.get('execution_rate', 0) or 0):.1%}",
        f"- Average delay: {float(summary.get('avg_delay_days', 0) or 0):.1f} days",
        f"- Average price deviation: {float(summary.get('avg_price_deviation_pct', 0) or 0):.2%}",
    ]
    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(["", "| Date | Symbol | Type | Status | Required | Executed | Delay |", "| --- | --- | --- | --- | ---: | ---: | ---: |"])
        for item in records:
            if int(item.get("required_quantity", 0) or 0) <= 0:
                continue
            delay = item.get("delay_days")
            lines.append(
                f"| {item.get('plan_date', '')} | {item.get('symbol', '')} | {item.get('plan_type', '')} | "
                f"{item.get('execution_status', '')} | {int(item.get('required_quantity', 0) or 0)} | "
                f"{int(item.get('executed_quantity', 0) or 0)} | {'' if delay is None else int(delay)} |"
            )
    action_items = list(summary.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "Action items:"])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def render_exit_execution_markdown(summary: dict | None) -> str:
    return "\n".join(["# Exit Execution Audit", "", *render_exit_execution_lines(summary), ""])


def summarize_lot_exit_execution(
    exit_plan_records: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    *,
    lookahead_days: int = 3,
    limit: int = 20,
) -> dict[str, Any]:
    closed_lots = build_lot_book(trade_records).to_dict().get("closed_lots", [])
    audits = _audit_lot_exit_records(exit_plan_records, closed_lots, lookahead_days=max(int(lookahead_days), 0))
    actionable = [item for item in audits if item["required_quantity"] > 0]
    executed = [item for item in actionable if item["execution_status"] == "executed"]
    partial = [item for item in actionable if item["execution_status"] == "partial"]
    missed = [item for item in actionable if item["execution_status"] == "missed"]
    delays = [float(item["delay_days"]) for item in actionable if item.get("delay_days") is not None]
    deviations = [float(item["price_deviation_pct"]) for item in actionable if item.get("price_deviation_pct") is not None]
    visible_limit = max(int(limit), 0)
    return {
        "total_items": len(audits),
        "actionable_count": len(actionable),
        "executed_count": len(executed),
        "partial_count": len(partial),
        "missed_count": len(missed),
        "execution_rate": len(executed) / len(actionable) if actionable else 0.0,
        "avg_delay_days": sum(delays) / len(delays) if delays else 0.0,
        "avg_price_deviation_pct": sum(deviations) / len(deviations) if deviations else 0.0,
        "records": audits[-visible_limit:] if visible_limit else audits,
        "action_items": _lot_execution_action_items(len(actionable), len(executed), len(partial), len(missed), deviations),
    }


def render_lot_exit_execution_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("actionable_count", 0) or 0) == 0:
        return ["- No actionable lot-level exit plans have been recorded yet."]
    lines = [
        f"- Actionable lot exits: {int(summary.get('actionable_count', 0) or 0)}",
        f"- Executed / partial / missed: {int(summary.get('executed_count', 0) or 0)} / {int(summary.get('partial_count', 0) or 0)} / {int(summary.get('missed_count', 0) or 0)}",
        f"- Execution rate: {float(summary.get('execution_rate', 0) or 0):.1%}",
        f"- Average delay: {float(summary.get('avg_delay_days', 0) or 0):.1f} days",
        f"- Average lot price deviation: {float(summary.get('avg_price_deviation_pct', 0) or 0):.2%}",
    ]
    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(["", "| Date | Symbol | Lot | Type | Status | Required | Executed |", "| --- | --- | --- | --- | --- | ---: | ---: |"])
        for item in records:
            if int(item.get("required_quantity", 0) or 0) <= 0:
                continue
            lines.append(
                f"| {item.get('plan_date', '')} | {item.get('symbol', '')} | {item.get('lot_id', '')} | "
                f"{item.get('plan_type', '')} | {item.get('execution_status', '')} | "
                f"{int(item.get('required_quantity', 0) or 0)} | {int(item.get('executed_quantity', 0) or 0)} |"
            )
    action_items = list(summary.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "Action items:"])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def render_lot_exit_execution_markdown(summary: dict | None) -> str:
    return "\n".join(["# Lot Exit Execution Audit", "", *render_lot_exit_execution_lines(summary), ""])


def _build_exit_item(
    position,
    *,
    stop_price: float | None,
    target_price: float | None,
    invalidated_reason: str | None,
    entry_date: date | None,
    current_date: date,
    max_position_pct: float,
    max_holding_days: int,
    time_stop_min_return_pct: float,
    profit_take_pct: float,
) -> ExitPlanItem:
    market_price = position.market_price
    holding_days = (current_date - entry_date).days if entry_date is not None else None
    base = {
        "symbol": position.symbol,
        "name": position.name,
        "current_quantity": position.quantity,
        "market_price": market_price,
        "avg_cost": position.avg_cost,
        "stop_price": stop_price,
        "target_price": target_price,
        "unrealized_return": position.unrealized_return,
        "exposure_pct": position.exposure_pct,
        "holding_days": holding_days,
    }
    if market_price is None:
        return ExitPlanItem(
            **base,
            plan_type="missing_price",
            action="watch",
            status="warn",
            priority=70,
            reason="Current price is missing; refresh quotes before deciding an exit.",
            sell_quantity=0,
            target_quantity=position.quantity,
            expected_cash_release=0.0,
        )
    if invalidated_reason:
        return _sell_all(base, "strategy_invalidated", "block", 110, f"Strategy thesis invalidated: {invalidated_reason}.")
    if stop_price is not None and market_price <= stop_price:
        return _sell_all(base, "stop_loss", "block", 100, f"Market price {market_price:.2f} is at or below stop {stop_price:.2f}.")
    if target_price is not None and market_price >= target_price:
        sell_quantity = _partial_sell_quantity(position.quantity, profit_take_pct)
        return _sell_partial(
            base,
            "take_profit",
            "warn",
            85,
            sell_quantity,
            f"Market price {market_price:.2f} has reached target {target_price:.2f}; lock in part of the profit.",
        )
    if position.exposure_pct is not None and position.exposure_pct > max_position_pct:
        target_quantity = _quantity_for_exposure(position, max_position_pct * 0.95)
        sell_quantity = max(position.quantity - target_quantity, 0)
        return _sell_partial(
            base,
            "reduce",
            "warn",
            80,
            sell_quantity,
            f"Position exposure {position.exposure_pct:.1%} is above limit {max_position_pct:.1%}; reduce to cap.",
        )
    if holding_days is not None and holding_days >= max_holding_days and (position.unrealized_return or 0.0) <= time_stop_min_return_pct:
        return _sell_all(
            base,
            "time_stop",
            "warn",
            75,
            f"Holding period {holding_days} days exceeded {max_holding_days} days without enough return.",
        )
    if stop_price is not None:
        distance = market_price / stop_price - 1.0
        if distance <= 0.03:
            return ExitPlanItem(
                **base,
                plan_type="near_stop",
                action="watch",
                status="warn",
                priority=60,
                reason=f"Only {distance:.1%} above stop; do not add before risk clears.",
                sell_quantity=0,
                target_quantity=position.quantity,
                expected_cash_release=0.0,
            )
    return ExitPlanItem(
        **base,
        plan_type="hold",
        action="hold",
        status="pass",
        priority=10,
        reason="No exit rule triggered; keep tracking the original plan.",
        sell_quantity=0,
        target_quantity=position.quantity,
        expected_cash_release=0.0,
    )


def _build_lot_exit_item(
    lot: dict[str, Any],
    *,
    stop_price: float | None,
    target_price: float | None,
    invalidated_reason: str | None,
    current_date: date,
    max_holding_days: int,
    time_stop_min_return_pct: float,
    profit_take_pct: float,
) -> ExitPlanItem:
    symbol = str(lot.get("symbol", "") or "").zfill(6)
    market_price = _float_or_none(lot.get("market_price"))
    entry_price = _float_or_none(lot.get("entry_price"))
    quantity = int(lot.get("remaining_quantity", lot.get("current_quantity", 0)) or 0)
    entry_date = str(lot.get("entry_date", "") or "")
    holding_days = lot.get("holding_days")
    if holding_days in (None, ""):
        parsed_entry = _parse_date(entry_date)
        holding_days = (current_date - parsed_entry).days if parsed_entry is not None else None
    else:
        holding_days = int(holding_days)
    unrealized_return = _float_or_none(lot.get("unrealized_return"))
    if unrealized_return is None and market_price is not None and entry_price not in (None, 0):
        unrealized_return = market_price / float(entry_price) - 1.0
    base = {
        "symbol": symbol,
        "name": str(lot.get("name", "") or ""),
        "current_quantity": quantity,
        "market_price": market_price,
        "avg_cost": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "unrealized_return": unrealized_return,
        "exposure_pct": None,
        "holding_days": holding_days,
        "lot_id": str(lot.get("lot_id", "") or ""),
        "entry_date": entry_date,
    }
    if quantity <= 0:
        return ExitPlanItem(
            **base,
            plan_type="empty_lot",
            action="hold",
            status="pass",
            priority=0,
            reason="Lot has no remaining quantity.",
            sell_quantity=0,
            target_quantity=0,
            expected_cash_release=0.0,
        )
    if market_price is None:
        return ExitPlanItem(
            **base,
            plan_type="missing_price",
            action="watch",
            status="warn",
            priority=70,
            reason="Lot current price is missing; refresh quotes before deciding an exit.",
            sell_quantity=0,
            target_quantity=quantity,
            expected_cash_release=0.0,
        )
    if invalidated_reason:
        return _sell_all(base, "strategy_invalidated", "block", 110, f"Lot thesis invalidated: {invalidated_reason}.")
    if stop_price is not None and market_price <= stop_price:
        return _sell_all(base, "stop_loss", "block", 100, f"Lot price {market_price:.2f} is at or below stop {stop_price:.2f}.")
    if target_price is not None and market_price >= target_price:
        sell_quantity = _partial_sell_quantity(quantity, profit_take_pct)
        return _sell_partial(
            base,
            "take_profit",
            "warn",
            85,
            sell_quantity,
            f"Lot price {market_price:.2f} has reached target {target_price:.2f}; take partial profit from this batch.",
        )
    if holding_days is not None and holding_days >= max_holding_days and (unrealized_return or 0.0) <= time_stop_min_return_pct:
        return _sell_all(
            base,
            "time_stop",
            "warn",
            75,
            f"Lot has been held {holding_days} days without enough return.",
        )
    if stop_price is not None:
        distance = market_price / stop_price - 1.0
        if distance <= 0.03:
            return ExitPlanItem(
                **base,
                plan_type="near_stop",
                action="watch",
                status="warn",
                priority=60,
                reason=f"Lot is only {distance:.1%} above stop; do not add before risk clears.",
                sell_quantity=0,
                target_quantity=quantity,
                expected_cash_release=0.0,
            )
    return ExitPlanItem(
        **base,
        plan_type="hold",
        action="hold",
        status="pass",
        priority=10,
        reason="No lot-level exit rule triggered.",
        sell_quantity=0,
        target_quantity=quantity,
        expected_cash_release=0.0,
    )


def _sell_all(base: dict[str, Any], plan_type: str, status: str, priority: int, reason: str) -> ExitPlanItem:
    quantity = int(base["current_quantity"])
    price = float(base.get("market_price") or 0.0)
    return ExitPlanItem(
        **base,
        plan_type=plan_type,
        action="sell_all",
        status=status,
        priority=priority,
        reason=reason,
        sell_quantity=quantity,
        target_quantity=0,
        expected_cash_release=round(quantity * price, 2),
    )


def _sell_partial(
    base: dict[str, Any],
    plan_type: str,
    status: str,
    priority: int,
    sell_quantity: int,
    reason: str,
) -> ExitPlanItem:
    quantity = int(base["current_quantity"])
    sell_quantity = min(max(int(sell_quantity), 0), quantity)
    target_quantity = quantity - sell_quantity
    price = float(base.get("market_price") or 0.0)
    return ExitPlanItem(
        **base,
        plan_type=plan_type,
        action="sell_partial" if sell_quantity < quantity else "sell_all",
        status=status,
        priority=priority,
        reason=reason,
        sell_quantity=sell_quantity,
        target_quantity=target_quantity,
        expected_cash_release=round(sell_quantity * price, 2),
    )


def _partial_sell_quantity(quantity: int, pct: float) -> int:
    raw = max(int(quantity * max(min(pct, 1.0), 0.0)), 0)
    if raw <= 0:
        return 0
    if quantity < 200:
        return quantity
    lots = floor(raw / 100) * 100
    if lots <= 0:
        lots = 100
    return min(lots, quantity)


def _quantity_for_exposure(position, target_pct: float) -> int:
    if position.market_price is None or position.market_price <= 0 or not position.exposure_pct:
        return position.quantity
    cash = (position.market_value or 0.0) / position.exposure_pct
    raw_quantity = cash * max(target_pct, 0.0) / position.market_price
    if raw_quantity < 100:
        return 0
    return int(floor(raw_quantity / 100) * 100)


def _audit_exit_records(
    exit_plan_records: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    *,
    lookahead_days: int,
) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for plan in exit_plan_records:
        plan_date = str(plan.get("plan_date", plan.get("date", "")) or "")[:10]
        for item in list(plan.get("items", []) or []):
            audits.append(_audit_one_exit(item, plan_date, trade_records, lookahead_days=lookahead_days))
    return audits


def _audit_lot_exit_records(
    exit_plan_records: list[dict[str, Any]],
    closed_lots: list[dict[str, Any]],
    *,
    lookahead_days: int,
) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for plan in exit_plan_records:
        plan_date = str(plan.get("plan_date", plan.get("date", "")) or "")[:10]
        for item in list(plan.get("items", []) or []):
            lot_id = str(item.get("lot_id", "") or "")
            if not lot_id:
                continue
            audits.append(_audit_one_lot_exit(item, plan_date, closed_lots, lookahead_days=lookahead_days))
    return audits


def _audit_one_exit(
    item: dict[str, Any],
    plan_date: str,
    trade_records: list[dict[str, Any]],
    *,
    lookahead_days: int,
) -> dict[str, Any]:
    symbol = str(item.get("symbol", "") or "").zfill(6)
    required_quantity = int(item.get("sell_quantity", 0) or 0)
    reference_price = _float_or_none(item.get("market_price"))
    trades = _matching_sell_trades(trade_records, symbol=symbol, plan_date=plan_date, lookahead_days=lookahead_days)
    executed_quantity = sum(int(trade.get("quantity", 0) or 0) for trade in trades)
    avg_trade_price = _weighted_avg_price(trades)
    status = _execution_status(required_quantity, executed_quantity)
    delay_days = _delay_days(plan_date, trades[0]) if trades else None
    price_deviation_pct = None
    if reference_price not in (None, 0) and avg_trade_price is not None:
        price_deviation_pct = avg_trade_price / reference_price - 1.0
    return {
        "plan_date": plan_date,
        "symbol": symbol,
        "name": str(item.get("name", "") or ""),
        "plan_type": str(item.get("plan_type", "") or ""),
        "action": str(item.get("action", "") or ""),
        "reason": str(item.get("reason", "") or ""),
        "execution_status": status,
        "required_quantity": required_quantity,
        "executed_quantity": executed_quantity,
        "execution_ratio": min(executed_quantity / required_quantity, 1.0) if required_quantity > 0 else 0.0,
        "delay_days": delay_days,
        "reference_price": reference_price,
        "avg_trade_price": avg_trade_price,
        "price_deviation_pct": price_deviation_pct,
        "matched_trades": trades,
    }


def _audit_one_lot_exit(
    item: dict[str, Any],
    plan_date: str,
    closed_lots: list[dict[str, Any]],
    *,
    lookahead_days: int,
) -> dict[str, Any]:
    lot_id = str(item.get("lot_id", "") or "")
    symbol = str(item.get("symbol", "") or "").zfill(6)
    required_quantity = int(item.get("sell_quantity", 0) or 0)
    reference_price = _float_or_none(item.get("market_price"))
    matched_lots = _matching_closed_lots(closed_lots, lot_id=lot_id, plan_date=plan_date, lookahead_days=lookahead_days)
    executed_quantity = sum(int(lot.get("quantity", 0) or 0) for lot in matched_lots)
    avg_exit_price = _weighted_avg_exit_price(matched_lots)
    delay_days = _lot_delay_days(plan_date, matched_lots[0]) if matched_lots else None
    status = _execution_status(required_quantity, executed_quantity)
    price_deviation_pct = None
    if reference_price not in (None, 0) and avg_exit_price is not None:
        price_deviation_pct = avg_exit_price / reference_price - 1.0
    return {
        "plan_date": plan_date,
        "symbol": symbol,
        "lot_id": lot_id,
        "entry_date": str(item.get("entry_date", "") or ""),
        "plan_type": str(item.get("plan_type", "") or ""),
        "action": str(item.get("action", "") or ""),
        "reason": str(item.get("reason", "") or ""),
        "execution_status": status,
        "required_quantity": required_quantity,
        "executed_quantity": executed_quantity,
        "execution_ratio": min(executed_quantity / required_quantity, 1.0) if required_quantity > 0 else 0.0,
        "delay_days": delay_days,
        "reference_price": reference_price,
        "avg_trade_price": avg_exit_price,
        "price_deviation_pct": price_deviation_pct,
        "matched_lots": matched_lots,
    }


def _matching_sell_trades(
    trade_records: list[dict[str, Any]],
    *,
    symbol: str,
    plan_date: str,
    lookahead_days: int,
) -> list[dict[str, Any]]:
    start = _parse_date(plan_date)
    if start is None:
        return []
    matches: list[dict[str, Any]] = []
    for trade in trade_records:
        if str(trade.get("symbol", "") or "").zfill(6) != symbol:
            continue
        if str(trade.get("side", "") or "").upper() != "SELL":
            continue
        trade_date = _parse_date(str(trade.get("date", trade.get("trade_date", "")) or "")[:10])
        if trade_date is None:
            continue
        delta_days = (trade_date - start).days
        if 0 <= delta_days <= lookahead_days:
            matches.append(trade)
    return sorted(matches, key=lambda item: str(item.get("date", item.get("trade_date", "")) or ""))


def _matching_closed_lots(
    closed_lots: list[dict[str, Any]],
    *,
    lot_id: str,
    plan_date: str,
    lookahead_days: int,
) -> list[dict[str, Any]]:
    start = _parse_date(plan_date)
    if start is None:
        return []
    matches: list[dict[str, Any]] = []
    for lot in closed_lots:
        if str(lot.get("lot_id", "") or "") != lot_id:
            continue
        exit_date = _parse_date(str(lot.get("exit_date", "") or "")[:10])
        if exit_date is None:
            continue
        delta_days = (exit_date - start).days
        if 0 <= delta_days <= lookahead_days:
            matches.append(lot)
    return sorted(matches, key=lambda item: str(item.get("exit_date", "") or ""))


def _execution_status(required_quantity: int, executed_quantity: int) -> str:
    if required_quantity <= 0:
        return "not_required"
    if executed_quantity >= required_quantity:
        return "executed"
    if executed_quantity > 0:
        return "partial"
    return "missed"


def _weighted_avg_price(trades: list[dict[str, Any]]) -> float | None:
    total_quantity = sum(int(trade.get("quantity", 0) or 0) for trade in trades)
    if total_quantity <= 0:
        return None
    total_amount = sum(float(trade.get("price", 0) or 0) * int(trade.get("quantity", 0) or 0) for trade in trades)
    return total_amount / total_quantity


def _weighted_avg_exit_price(closed_lots: list[dict[str, Any]]) -> float | None:
    total_quantity = sum(int(lot.get("quantity", 0) or 0) for lot in closed_lots)
    if total_quantity <= 0:
        return None
    total_amount = sum(float(lot.get("exit_price", 0) or 0) * int(lot.get("quantity", 0) or 0) for lot in closed_lots)
    return total_amount / total_quantity


def _delay_days(plan_date: str, trade: dict[str, Any]) -> int | None:
    start = _parse_date(plan_date)
    end = _parse_date(str(trade.get("date", trade.get("trade_date", "")) or "")[:10])
    if start is None or end is None:
        return None
    return (end - start).days


def _lot_delay_days(plan_date: str, closed_lot: dict[str, Any]) -> int | None:
    start = _parse_date(plan_date)
    end = _parse_date(str(closed_lot.get("exit_date", "") or "")[:10])
    if start is None or end is None:
        return None
    return (end - start).days


def _normalize_price_map(values: dict[str, float] | None) -> dict[str, float]:
    return {str(key).zfill(6): float(value) for key, value in (values or {}).items()}


def _parse_date(value: str | None) -> date | None:
    try:
        return datetime.fromisoformat(str(value or "")[:10]).date()
    except ValueError:
        return None


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rollup_status(items: list[ExitPlanItem]) -> str:
    statuses = {item.status for item in items}
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _action_items(items: list[ExitPlanItem], status: str, expected_cash_release: float) -> list[str]:
    items_to_sell = [item for item in items if item.sell_quantity > 0]
    blockers = [item for item in items_to_sell if item.status == "block"]
    warnings = [item for item in items_to_sell if item.status == "warn"]
    notes: list[str] = []
    if blockers:
        notes.append(f"Handle {len(blockers)} blocking exits before considering any new BUY.")
    if warnings:
        notes.append(f"Review {len(warnings)} planned sells/reductions during the next session.")
    if expected_cash_release:
        notes.append(f"Expected cash release is about {expected_cash_release:.2f}; update position book after trades settle.")
    if status == "pass":
        notes.append("No exit rule triggered; keep stops, targets, and thesis notes updated.")
    return notes


def _execution_action_items(
    actionable_count: int,
    executed_count: int,
    partial_count: int,
    missed_count: int,
    deviations: list[float],
) -> list[str]:
    notes: list[str] = []
    if missed_count:
        notes.append(f"{missed_count} planned exits were not matched by SELL trades; review discipline before opening new risk.")
    if partial_count:
        notes.append(f"{partial_count} planned exits were only partially executed; confirm the remaining quantity.")
    if actionable_count and executed_count == actionable_count:
        notes.append("All actionable exits have matching SELL trades.")
    if deviations and abs(sum(deviations) / len(deviations)) >= 0.03:
        notes.append("Average exit execution price deviated by at least 3%; review slippage, hesitation, or liquidity.")
    if not notes:
        notes.append("No obvious exit execution issue.")
    return notes


def _lot_execution_action_items(
    actionable_count: int,
    executed_count: int,
    partial_count: int,
    missed_count: int,
    deviations: list[float],
) -> list[str]:
    notes: list[str] = []
    if missed_count:
        notes.append(f"{missed_count} planned lot exits did not match closed lots; confirm whether the wrong batch was sold.")
    if partial_count:
        notes.append(f"{partial_count} planned lot exits were only partially closed; review remaining lot risk.")
    if actionable_count and executed_count == actionable_count:
        notes.append("All actionable lot-level exits matched the intended closed lots.")
    if deviations and abs(sum(deviations) / len(deviations)) >= 0.03:
        notes.append("Lot exit execution price deviated by at least 3%; review hesitation, liquidity, or slippage.")
    if not notes:
        notes.append("No obvious lot-level exit execution issue.")
    return notes
