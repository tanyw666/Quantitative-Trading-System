from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from math import floor
from pathlib import Path
from typing import Any

from quant_system.portfolio.positions import PositionBook
from quant_system.portfolio.risk_check import HoldingRiskReport
from quant_system.storage.jsonl import append_jsonl, read_jsonl


@dataclass(frozen=True)
class PositionAction:
    symbol: str
    name: str
    action: str
    status: str
    priority: int
    reason: str
    current_quantity: int
    target_quantity: int | None = None
    quantity_delta: int | None = None
    market_price: float | None = None
    stop_price: float | None = None
    current_exposure_pct: float | None = None
    target_exposure_pct: float | None = None
    estimated_cash_change: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PositionActionPlan:
    created_at: str
    action_date: str
    status: str
    total_actions: int
    exit_count: int
    reduce_count: int
    watch_count: int
    hold_count: int
    actions: list[PositionAction]
    action_items: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["actions"] = [action.to_dict() for action in self.actions]
        return data


def build_position_action_plan(
    book: PositionBook,
    risk_report: HoldingRiskReport | dict[str, Any],
    *,
    stops: dict[str, float] | None = None,
    max_exposure_pct: float = 0.8,
    max_position_pct: float = 0.2,
    target_exposure_pct: float | None = None,
) -> PositionActionPlan:
    stops = {str(key).zfill(6): float(value) for key, value in (stops or {}).items()}
    risk_status = _risk_status(risk_report)
    exposure_cap = _effective_total_cap(max_exposure_pct, target_exposure_pct)
    actions: list[PositionAction] = []

    forced_cash = 0.0
    for position in book.positions:
        action = _position_action(
            position=position,
            stops=stops,
            max_position_pct=max_position_pct,
            risk_status=risk_status,
        )
        if action:
            actions.append(action)
            forced_cash += float(action.estimated_cash_change or 0.0)

    remaining_market_value = max(0.0, book.total_market_value - forced_cash)
    allowed_market_value = book.cash * exposure_cap
    if exposure_cap >= 0 and remaining_market_value > allowed_market_value * 1.05:
        trim_value = remaining_market_value - allowed_market_value
        actions = _add_total_exposure_reductions(
            actions,
            book=book,
            trim_value=trim_value,
            max_position_pct=max_position_pct,
            exposure_cap=exposure_cap,
        )

    existing_symbols = {action.symbol for action in actions}
    for position in book.positions:
        if position.symbol in existing_symbols:
            continue
        actions.append(
            PositionAction(
                symbol=position.symbol,
                name=position.name,
                action="hold",
                status="pass",
                priority=10,
                reason="持仓未触发止损、暴露或价格缺失规则，按计划继续跟踪。",
                current_quantity=position.quantity,
                target_quantity=position.quantity,
                quantity_delta=0,
                market_price=position.market_price,
                stop_price=stops.get(position.symbol),
                current_exposure_pct=position.exposure_pct,
                target_exposure_pct=position.exposure_pct,
                estimated_cash_change=0.0,
            )
        )

    actions = sorted(actions, key=lambda item: (-item.priority, item.symbol))
    status = _rollup_status(risk_status, actions)
    exit_count = sum(1 for item in actions if item.action == "exit")
    reduce_count = sum(1 for item in actions if item.action == "reduce")
    watch_count = sum(1 for item in actions if item.action == "watch")
    hold_count = sum(1 for item in actions if item.action == "hold")
    return PositionActionPlan(
        created_at=datetime.now(timezone.utc).isoformat(),
        action_date=date.today().isoformat(),
        status=status,
        total_actions=len(actions),
        exit_count=exit_count,
        reduce_count=reduce_count,
        watch_count=watch_count,
        hold_count=hold_count,
        actions=actions,
        action_items=_action_items(status, exit_count, reduce_count, watch_count, exposure_cap, book.total_exposure_pct),
    )


def render_position_action_plan_lines(plan: dict[str, Any] | PositionActionPlan | None) -> list[str]:
    payload = plan.to_dict() if isinstance(plan, PositionActionPlan) else (plan or {})
    if not payload:
        return ["- 暂无持仓动作计划。"]
    actions = list(payload.get("actions", []) or [])
    if not actions:
        return ["- 暂无持仓动作计划。"]

    lines = [
        f"- 总状态：{payload.get('status', '')}",
        f"- 动作统计：清仓 {int(payload.get('exit_count', 0) or 0)}，减仓 {int(payload.get('reduce_count', 0) or 0)}，观察 {int(payload.get('watch_count', 0) or 0)}，持有 {int(payload.get('hold_count', 0) or 0)}",
        "",
        "| Symbol | Action | Status | Qty | Target | Reason |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in actions:
        target = item.get("target_quantity")
        lines.append(
            f"| {item.get('symbol', '')} | {item.get('action', '')} | {item.get('status', '')} | "
            f"{int(item.get('current_quantity', 0) or 0)} | "
            f"{'' if target is None else int(target)} | {item.get('reason', '')} |"
        )
    action_items = list(payload.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "行动清单："])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def append_position_action_plan_record(path: Path, plan: PositionActionPlan | dict[str, Any]) -> None:
    payload = plan.to_dict() if isinstance(plan, PositionActionPlan) else dict(plan)
    append_jsonl(path, payload)


def read_position_action_plan_records(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def _position_action(
    *,
    position,
    stops: dict[str, float],
    max_position_pct: float,
    risk_status: str,
) -> PositionAction | None:
    stop_price = stops.get(position.symbol)
    market_price = position.market_price
    exposure_pct = position.exposure_pct

    if market_price is None:
        return PositionAction(
            symbol=position.symbol,
            name=position.name,
            action="watch",
            status="warn",
            priority=70,
            reason="缺少当前价格，无法判断止损和暴露，先补行情再决策。",
            current_quantity=position.quantity,
            market_price=None,
            stop_price=stop_price,
            current_exposure_pct=exposure_pct,
        )

    if stop_price is not None and market_price <= stop_price:
        return PositionAction(
            symbol=position.symbol,
            name=position.name,
            action="exit",
            status="block",
            priority=100,
            reason=f"当前价 {market_price:.2f} 已触发止损 {stop_price:.2f}，优先处理。",
            current_quantity=position.quantity,
            target_quantity=0,
            quantity_delta=-position.quantity,
            market_price=market_price,
            stop_price=stop_price,
            current_exposure_pct=exposure_pct,
            target_exposure_pct=0.0,
            estimated_cash_change=market_price * position.quantity,
        )

    if exposure_pct is not None and exposure_pct > max_position_pct:
        target_quantity = _quantity_for_exposure(position, max_position_pct * 0.95)
        target_quantity = min(target_quantity, position.quantity)
        delta = target_quantity - position.quantity
        return PositionAction(
            symbol=position.symbol,
            name=position.name,
            action="reduce",
            status="block" if risk_status == "block" else "warn",
            priority=85,
            reason=f"单票暴露 {exposure_pct:.1%} 超过上限 {max_position_pct:.1%}，需要降到上限以内。",
            current_quantity=position.quantity,
            target_quantity=target_quantity,
            quantity_delta=delta,
            market_price=market_price,
            stop_price=stop_price,
            current_exposure_pct=exposure_pct,
            target_exposure_pct=_target_exposure(position, target_quantity),
            estimated_cash_change=abs(delta) * market_price,
        )

    if stop_price is not None:
        distance = market_price / stop_price - 1.0
        if distance <= 0.03:
            return PositionAction(
                symbol=position.symbol,
                name=position.name,
                action="watch",
                status="warn",
                priority=60,
                reason=f"距离止损仅 {distance:.1%}，盘中必须盯紧，禁止加仓。",
                current_quantity=position.quantity,
                target_quantity=position.quantity,
                quantity_delta=0,
                market_price=market_price,
                stop_price=stop_price,
                current_exposure_pct=exposure_pct,
                target_exposure_pct=exposure_pct,
                estimated_cash_change=0.0,
            )

    return None


def _add_total_exposure_reductions(
    actions: list[PositionAction],
    *,
    book: PositionBook,
    trim_value: float,
    max_position_pct: float,
    exposure_cap: float,
) -> list[PositionAction]:
    by_symbol = {action.symbol: action for action in actions}
    remaining_trim = trim_value
    ordered = sorted(
        [position for position in book.positions if position.market_price is not None],
        key=lambda item: float(item.market_value or 0.0),
        reverse=True,
    )
    for position in ordered:
        if remaining_trim <= 0:
            break
        if by_symbol.get(position.symbol, None) and by_symbol[position.symbol].action == "exit":
            continue
        market_price = float(position.market_price or 0.0)
        if market_price <= 0:
            continue
        target_value = max(0.0, float(position.market_value or 0.0) - remaining_trim)
        target_pct = min(max_position_pct * 0.95, target_value / book.cash if book.cash else 0.0)
        target_quantity = min(position.quantity, _quantity_for_exposure(position, target_pct))
        delta = target_quantity - position.quantity
        if delta >= 0:
            continue
        cash_change = abs(delta) * market_price
        remaining_trim -= cash_change
        action = PositionAction(
            symbol=position.symbol,
            name=position.name,
            action="reduce",
            status="warn",
            priority=75,
            reason=f"总暴露高于目标 {exposure_cap:.1%}，按市值从高到低释放风险。",
            current_quantity=position.quantity,
            target_quantity=target_quantity,
            quantity_delta=delta,
            market_price=market_price,
            current_exposure_pct=position.exposure_pct,
            target_exposure_pct=target_quantity * market_price / book.cash if book.cash else None,
            estimated_cash_change=cash_change,
        )
        previous = by_symbol.get(position.symbol)
        if previous is None or action.priority > previous.priority:
            by_symbol[position.symbol] = action
    return list(by_symbol.values())


def _quantity_for_exposure(position, target_pct: float) -> int:
    if position.market_price is None or position.market_price <= 0 or not position.exposure_pct:
        return position.quantity
    cash = (position.market_value or 0.0) / position.exposure_pct
    raw_quantity = cash * max(target_pct, 0.0) / position.market_price
    if raw_quantity < 100:
        return 0
    return int(floor(raw_quantity / 100) * 100)


def _target_exposure(position, target_quantity: int) -> float | None:
    if position.market_price is None or position.market_price <= 0 or not position.exposure_pct:
        return None
    cash = (position.market_value or 0.0) / position.exposure_pct
    if not cash:
        return None
    return target_quantity * position.market_price / cash


def _risk_status(risk_report: HoldingRiskReport | dict[str, Any]) -> str:
    if isinstance(risk_report, HoldingRiskReport):
        return risk_report.status
    return str((risk_report or {}).get("status", "pass") or "pass")


def _effective_total_cap(max_exposure_pct: float, target_exposure_pct: float | None) -> float:
    if target_exposure_pct is None:
        return max_exposure_pct
    if target_exposure_pct <= 0:
        return 0.0
    return min(max_exposure_pct, target_exposure_pct)


def _rollup_status(risk_status: str, actions: list[PositionAction]) -> str:
    statuses = {action.status for action in actions}
    if "block" in statuses or risk_status == "block":
        return "block"
    if "warn" in statuses or risk_status == "warn":
        return "warn"
    return "pass"


def _action_items(
    status: str,
    exit_count: int,
    reduce_count: int,
    watch_count: int,
    exposure_cap: float,
    total_exposure_pct: float,
) -> list[str]:
    items: list[str] = []
    if exit_count:
        items.append(f"先处理 {exit_count} 个止损/清仓动作，再考虑任何新开仓。")
    if reduce_count:
        items.append(f"执行 {reduce_count} 个减仓动作，把总暴露从 {total_exposure_pct:.1%} 拉回目标 {exposure_cap:.1%} 附近。")
    if watch_count:
        items.append(f"{watch_count} 个持仓需要补行情或贴近止损监控，禁止对这些标的加仓。")
    if status == "pass":
        items.append("持仓动作计划无阻断项，继续按交易计划和盘前预检执行。")
    return items
