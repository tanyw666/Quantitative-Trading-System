from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import floor
from typing import Any

from quant_system.portfolio.positions import PositionBook


@dataclass(frozen=True)
class LifecycleRuleItem:
    symbol: str
    name: str
    phase: str
    status: str
    action: str
    reason: str
    current_quantity: int
    current_exposure_pct: float | None = None
    unrealized_return: float | None = None
    market_price: float | None = None
    stop_price: float | None = None
    distance_to_stop_pct: float | None = None
    add_allowed: bool = False
    add_blocked: bool = False
    add_quantity: int = 0
    reduce_quantity: int = 0
    target_quantity: int | None = None
    rule_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LifecycleRulePlan:
    status: str
    total_positions: int
    add_count: int
    reduce_count: int
    exit_count: int
    hold_count: int
    blocked_add_count: int
    probe_count: int
    build_count: int
    core_count: int
    items: list[LifecycleRuleItem]
    action_items: list[str]
    exception_penalty: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["items"] = [item.to_dict() for item in self.items]
        return data


def build_lifecycle_rule_plan(
    book: PositionBook,
    *,
    stops: dict[str, float] | None = None,
    discipline_summary: dict[str, Any] | None = None,
    max_probe_pct: float = 0.05,
    max_position_pct: float = 0.2,
    add_step_pct: float = 0.05,
    add_profit_trigger_pct: float = 0.03,
    reduce_loss_warning_pct: float = 0.03,
    near_stop_pct: float = 0.03,
    exception_warn_threshold: int = 1,
    exception_block_threshold: int = 2,
) -> LifecycleRulePlan:
    stop_map = {str(key).zfill(6): float(value) for key, value in (stops or {}).items()}
    exception_penalty = _build_exception_penalty(
        discipline_summary or {},
        warn_threshold=exception_warn_threshold,
        block_threshold=exception_block_threshold,
    )
    items = [
        _build_rule_item(
            position,
            stop_price=stop_map.get(position.symbol),
            max_probe_pct=max_probe_pct,
            max_position_pct=max_position_pct,
            add_step_pct=add_step_pct,
            add_profit_trigger_pct=add_profit_trigger_pct,
            reduce_loss_warning_pct=reduce_loss_warning_pct,
            near_stop_pct=near_stop_pct,
            exception_penalty=exception_penalty,
        )
        for position in book.positions
    ]
    statuses = {item.status for item in items}
    status = "block" if "block" in statuses or exception_penalty["status"] == "block" else "warn" if "warn" in statuses or exception_penalty["status"] == "warn" else "pass"
    add_count = sum(1 for item in items if item.action == "add")
    reduce_count = sum(1 for item in items if item.action == "reduce")
    exit_count = sum(1 for item in items if item.action == "exit")
    hold_count = sum(1 for item in items if item.action == "hold")
    blocked_add_count = sum(1 for item in items if item.add_blocked)
    probe_count = sum(1 for item in items if item.phase == "probe")
    build_count = sum(1 for item in items if item.phase == "build")
    core_count = sum(1 for item in items if item.phase == "core")
    return LifecycleRulePlan(
        status=status,
        total_positions=len(items),
        add_count=add_count,
        reduce_count=reduce_count,
        exit_count=exit_count,
        hold_count=hold_count,
        blocked_add_count=blocked_add_count,
        probe_count=probe_count,
        build_count=build_count,
        core_count=core_count,
        items=items,
        action_items=_action_items(items, exception_penalty, status=status),
        exception_penalty=exception_penalty,
    )


def render_lifecycle_rule_lines(plan: dict[str, Any] | LifecycleRulePlan | None) -> list[str]:
    payload = plan.to_dict() if isinstance(plan, LifecycleRulePlan) else (plan or {})
    if not payload:
        return ["- No lifecycle rule plan available."]
    lines = [
        f"- Status: {payload.get('status', '')}",
        (
            "- Probe / build / core: "
            f"{int(payload.get('probe_count', 0) or 0)} / "
            f"{int(payload.get('build_count', 0) or 0)} / "
            f"{int(payload.get('core_count', 0) or 0)}"
        ),
        (
            "- Add / reduce / exit / blocked-add: "
            f"{int(payload.get('add_count', 0) or 0)} / "
            f"{int(payload.get('reduce_count', 0) or 0)} / "
            f"{int(payload.get('exit_count', 0) or 0)} / "
            f"{int(payload.get('blocked_add_count', 0) or 0)}"
        ),
    ]
    penalty = dict(payload.get("exception_penalty") or {})
    if penalty and penalty.get("status") in {"warn", "block"}:
        lines.append(f"- Exception penalty: {penalty.get('status')} / {penalty.get('action')} / count={int(penalty.get('exception_count', 0) or 0)}")
    items = list(payload.get("items", []) or [])
    if items:
        lines.extend(["", "| Symbol | Phase | Action | Status | Add | Reduce | Reason |", "| --- | --- | --- | --- | ---: | ---: | --- |"])
        for item in items:
            lines.append(
                f"| {item.get('symbol', '')} | {item.get('phase', '')} | {item.get('action', '')} | "
                f"{item.get('status', '')} | {int(item.get('add_quantity', 0) or 0)} | "
                f"{int(item.get('reduce_quantity', 0) or 0)} | {item.get('reason', '')} |"
            )
    action_items = list(payload.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "Action items:"])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def _build_rule_item(
    position,
    *,
    stop_price: float | None,
    max_probe_pct: float,
    max_position_pct: float,
    add_step_pct: float,
    add_profit_trigger_pct: float,
    reduce_loss_warning_pct: float,
    near_stop_pct: float,
    exception_penalty: dict[str, Any],
) -> LifecycleRuleItem:
    phase = _phase(position.exposure_pct, max_probe_pct=max_probe_pct, max_position_pct=max_position_pct)
    exposure_pct = position.exposure_pct
    market_price = position.market_price
    unrealized_return = position.unrealized_return
    distance_to_stop_pct = _distance_to_stop_pct(market_price, stop_price)
    tags: list[str] = []

    if market_price is None:
        tags.append("missing_price")
        return LifecycleRuleItem(
            symbol=position.symbol,
            name=position.name,
            phase=phase,
            status="warn",
            action="hold",
            reason="Current price is missing; do not change the position before quotes refresh.",
            current_quantity=position.quantity,
            current_exposure_pct=exposure_pct,
            unrealized_return=unrealized_return,
            market_price=market_price,
            stop_price=stop_price,
            distance_to_stop_pct=distance_to_stop_pct,
            add_blocked=True,
            rule_tags=tags,
        )

    if stop_price is not None and market_price <= stop_price:
        tags.append("stop_broken")
        return LifecycleRuleItem(
            symbol=position.symbol,
            name=position.name,
            phase=phase,
            status="block",
            action="exit",
            reason=f"Price {market_price:.2f} is at or below stop {stop_price:.2f}; exit instead of negotiating.",
            current_quantity=position.quantity,
            current_exposure_pct=exposure_pct,
            unrealized_return=unrealized_return,
            market_price=market_price,
            stop_price=stop_price,
            distance_to_stop_pct=distance_to_stop_pct,
            add_blocked=True,
            reduce_quantity=position.quantity,
            target_quantity=0,
            rule_tags=tags,
        )

    if exposure_pct is not None and exposure_pct > max_position_pct:
        tags.append("over_position_limit")
        target_quantity = _quantity_for_exposure(position, max_position_pct * 0.9)
        reduce_quantity = max(position.quantity - target_quantity, 0)
        return LifecycleRuleItem(
            symbol=position.symbol,
            name=position.name,
            phase=phase,
            status="warn",
            action="reduce",
            reason=f"Exposure {exposure_pct:.1%} is above the position cap {max_position_pct:.1%}; cut back before thinking about adds.",
            current_quantity=position.quantity,
            current_exposure_pct=exposure_pct,
            unrealized_return=unrealized_return,
            market_price=market_price,
            stop_price=stop_price,
            distance_to_stop_pct=distance_to_stop_pct,
            add_blocked=True,
            reduce_quantity=reduce_quantity,
            target_quantity=target_quantity,
            rule_tags=tags,
        )

    if distance_to_stop_pct is not None and distance_to_stop_pct <= near_stop_pct:
        tags.extend(["near_stop", "average_down_forbidden"])
        target_quantity = _quantity_for_exposure(position, min(max_probe_pct, exposure_pct or max_probe_pct))
        reduce_quantity = max(position.quantity - target_quantity, 0)
        return LifecycleRuleItem(
            symbol=position.symbol,
            name=position.name,
            phase=phase,
            status="warn",
            action="reduce" if reduce_quantity > 0 else "hold",
            reason=f"Only {distance_to_stop_pct:.1%} above stop; cut risk and do not average down.",
            current_quantity=position.quantity,
            current_exposure_pct=exposure_pct,
            unrealized_return=unrealized_return,
            market_price=market_price,
            stop_price=stop_price,
            distance_to_stop_pct=distance_to_stop_pct,
            add_blocked=True,
            reduce_quantity=reduce_quantity,
            target_quantity=position.quantity - reduce_quantity if reduce_quantity > 0 else position.quantity,
            rule_tags=tags,
        )

    if unrealized_return is not None and unrealized_return <= -abs(reduce_loss_warning_pct):
        tags.extend(["loser", "average_down_forbidden"])
        target_quantity = _quantity_for_exposure(position, min(max_probe_pct, exposure_pct or max_probe_pct))
        reduce_quantity = max(position.quantity - target_quantity, 0)
        return LifecycleRuleItem(
            symbol=position.symbol,
            name=position.name,
            phase=phase,
            status="warn",
            action="reduce" if reduce_quantity > 0 else "hold",
            reason=f"Unrealized return {unrealized_return:.1%} is below the loss discipline line; reduce instead of averaging down.",
            current_quantity=position.quantity,
            current_exposure_pct=exposure_pct,
            unrealized_return=unrealized_return,
            market_price=market_price,
            stop_price=stop_price,
            distance_to_stop_pct=distance_to_stop_pct,
            add_blocked=True,
            reduce_quantity=reduce_quantity,
            target_quantity=position.quantity - reduce_quantity if reduce_quantity > 0 else position.quantity,
            rule_tags=tags,
        )

    can_add = (
        unrealized_return is not None
        and unrealized_return >= add_profit_trigger_pct
        and (distance_to_stop_pct is None or distance_to_stop_pct > near_stop_pct)
        and (exposure_pct or 0.0) < max_position_pct
    )
    add_quantity = 0
    if can_add:
        next_exposure = min(max_position_pct, max((exposure_pct or 0.0) + add_step_pct, max_probe_pct))
        add_quantity = max(_quantity_for_exposure(position, next_exposure) - position.quantity, 0)

    if can_add and add_quantity > 0:
        if exception_penalty["action"] == "pause_add":
            tags.extend(["exception_penalty", "add_paused"])
            return LifecycleRuleItem(
                symbol=position.symbol,
                name=position.name,
                phase=phase,
                status="block",
                action="hold",
                reason="Recent discipline exceptions are too frequent; no new add is allowed until the chain is clean again.",
                current_quantity=position.quantity,
                current_exposure_pct=exposure_pct,
                unrealized_return=unrealized_return,
                market_price=market_price,
                stop_price=stop_price,
                distance_to_stop_pct=distance_to_stop_pct,
                add_allowed=False,
                add_blocked=True,
                add_quantity=0,
                target_quantity=position.quantity,
                rule_tags=tags,
            )
        if exception_penalty["action"] == "cool_add":
            tags.extend(["exception_penalty", "add_cooled"])
            return LifecycleRuleItem(
                symbol=position.symbol,
                name=position.name,
                phase=phase,
                status="warn",
                action="hold",
                reason="Discipline exceptions are elevated; keep the winner but wait one more clean cycle before adding.",
                current_quantity=position.quantity,
                current_exposure_pct=exposure_pct,
                unrealized_return=unrealized_return,
                market_price=market_price,
                stop_price=stop_price,
                distance_to_stop_pct=distance_to_stop_pct,
                add_allowed=False,
                add_blocked=True,
                add_quantity=0,
                target_quantity=position.quantity,
                rule_tags=tags,
            )
        tags.append("winner_add")
        return LifecycleRuleItem(
            symbol=position.symbol,
            name=position.name,
            phase=phase,
            status="pass",
            action="add",
            reason=f"Winner confirmed with return {unrealized_return:.1%}; add only along strength, never on weakness.",
            current_quantity=position.quantity,
            current_exposure_pct=exposure_pct,
            unrealized_return=unrealized_return,
            market_price=market_price,
            stop_price=stop_price,
            distance_to_stop_pct=distance_to_stop_pct,
            add_allowed=True,
            add_quantity=add_quantity,
            target_quantity=position.quantity + add_quantity,
            rule_tags=tags,
        )

    tags.append("hold_plan")
    return LifecycleRuleItem(
        symbol=position.symbol,
        name=position.name,
        phase=phase,
        status="pass",
        action="hold",
        reason="Keep the current size and wait for either stronger confirmation or a clear exit trigger.",
        current_quantity=position.quantity,
        current_exposure_pct=exposure_pct,
        unrealized_return=unrealized_return,
        market_price=market_price,
        stop_price=stop_price,
        distance_to_stop_pct=distance_to_stop_pct,
        add_allowed=False,
        add_blocked=(unrealized_return or 0.0) < add_profit_trigger_pct,
        target_quantity=position.quantity,
        rule_tags=tags,
    )


def _phase(exposure_pct: float | None, *, max_probe_pct: float, max_position_pct: float) -> str:
    if exposure_pct in (None, ""):
        return "unknown"
    exposure = float(exposure_pct)
    if exposure <= max_probe_pct * 1.2:
        return "probe"
    if exposure <= max(max_probe_pct * 2.0, max_position_pct * 0.7):
        return "build"
    return "core"


def _distance_to_stop_pct(market_price: float | None, stop_price: float | None) -> float | None:
    if market_price in (None, "") or stop_price in (None, ""):
        return None
    if float(stop_price) <= 0:
        return None
    return float(market_price) / float(stop_price) - 1.0


def _quantity_for_exposure(position, target_pct: float) -> int:
    if position.market_price is None or position.market_price <= 0 or not position.exposure_pct:
        return position.quantity
    cash = (position.market_value or 0.0) / position.exposure_pct
    raw_quantity = cash * max(target_pct, 0.0) / position.market_price
    if raw_quantity < 100:
        return 0
    return int(floor(raw_quantity / 100) * 100)


def _build_exception_penalty(
    discipline_summary: dict[str, Any],
    *,
    warn_threshold: int,
    block_threshold: int,
) -> dict[str, Any]:
    exception_count = int(discipline_summary.get("discipline_exception_count", 0) or 0)
    if exception_count >= max(int(block_threshold), 1):
        return {
            "status": "block",
            "action": "pause_add",
            "exception_count": exception_count,
            "reason": "Too many discipline exceptions; stop pyramiding until a clean sequence is rebuilt.",
        }
    if exception_count >= max(int(warn_threshold), 1):
        return {
            "status": "warn",
            "action": "cool_add",
            "exception_count": exception_count,
            "reason": "Discipline exceptions are building up; slow down the next add.",
        }
    return {
        "status": "pass",
        "action": "keep",
        "exception_count": exception_count,
        "reason": "",
    }


def _action_items(items: list[LifecycleRuleItem], exception_penalty: dict[str, Any], *, status: str) -> list[str]:
    notes: list[str] = []
    if exception_penalty.get("status") == "block":
        notes.append("Discipline exceptions are too frequent; pause all adds until a clean trading sequence is restored.")
    elif exception_penalty.get("status") == "warn":
        notes.append("Discipline exceptions are elevated; delay the next add and demand a cleaner follow-through.")
    add_items = [item for item in items if item.action == "add"]
    if add_items:
        notes.append(f"{len(add_items)} position(s) may add only as winners, and only in planned lot sizes.")
    reduce_items = [item for item in items if item.action == "reduce"]
    if reduce_items:
        notes.append(f"{len(reduce_items)} position(s) should reduce before any new risk is opened.")
    exit_items = [item for item in items if item.action == "exit"]
    if exit_items:
        notes.append(f"{len(exit_items)} position(s) have already invalidated the stop discipline and should exit first.")
    if status == "pass" and not notes:
        notes.append("No lifecycle rule is blocking the current book; keep size unchanged unless a winner proves it can earn the next add.")
    return notes
