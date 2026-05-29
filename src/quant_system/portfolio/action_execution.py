from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from quant_system.portfolio.position_actions import read_position_action_plan_records


def summarize_action_execution(
    action_plan_records: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    *,
    lookahead_days: int = 3,
    limit: int = 20,
) -> dict[str, Any]:
    audits = _audit_action_records(action_plan_records, trade_records, lookahead_days=max(int(lookahead_days), 0))
    actionable = [item for item in audits if item["action"] in {"exit", "reduce"}]
    executed = [item for item in actionable if item["execution_status"] == "executed"]
    partial = [item for item in actionable if item["execution_status"] == "partial"]
    missed = [item for item in actionable if item["execution_status"] == "missed"]
    delays = [float(item["delay_days"]) for item in actionable if item.get("delay_days") is not None]
    deviations = [
        float(item["price_deviation_pct"])
        for item in actionable
        if item.get("price_deviation_pct") is not None
    ]
    visible_limit = max(int(limit), 0)
    return {
        "total_actions": len(audits),
        "actionable_count": len(actionable),
        "executed_count": len(executed),
        "partial_count": len(partial),
        "missed_count": len(missed),
        "execution_rate": len(executed) / len(actionable) if actionable else 0.0,
        "avg_delay_days": sum(delays) / len(delays) if delays else 0.0,
        "avg_price_deviation_pct": sum(deviations) / len(deviations) if deviations else 0.0,
        "records": audits[-visible_limit:] if visible_limit else audits,
        "action_items": _action_items(len(actionable), len(executed), len(partial), len(missed), deviations),
    }


def render_action_execution_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("actionable_count", 0) or 0) == 0:
        return ["- 暂无可审计的持仓动作。先记录 portfolio actions，再记录实际成交。"]
    lines = [
        f"- 可执行动作：{int(summary.get('actionable_count', 0) or 0)}",
        f"- 完整执行：{int(summary.get('executed_count', 0) or 0)}",
        f"- 部分执行：{int(summary.get('partial_count', 0) or 0)}",
        f"- 未执行：{int(summary.get('missed_count', 0) or 0)}",
        f"- 执行率：{float(summary.get('execution_rate', 0) or 0):.1%}",
        f"- 平均延迟：{float(summary.get('avg_delay_days', 0) or 0):.1f} 天",
        f"- 平均价格偏差：{float(summary.get('avg_price_deviation_pct', 0) or 0):.2%}",
    ]
    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(["", "| Date | Symbol | Action | Status | Qty | Executed | Delay |", "| --- | --- | --- | --- | ---: | ---: | ---: |"])
        for item in records:
            if item.get("action") not in {"exit", "reduce"}:
                continue
            delay = item.get("delay_days")
            lines.append(
                f"| {item.get('action_date', '')} | {item.get('symbol', '')} | {item.get('action', '')} | "
                f"{item.get('execution_status', '')} | {int(item.get('required_quantity', 0) or 0)} | "
                f"{int(item.get('executed_quantity', 0) or 0)} | {'' if delay is None else int(delay)} |"
            )
    action_items = list(summary.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "行动清单："])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def render_action_execution_markdown(summary: dict | None) -> str:
    return "\n".join(["# 持仓动作执行审计", "", *render_action_execution_lines(summary), ""])


def read_action_plan_records(path: Path) -> list[dict[str, Any]]:
    return read_position_action_plan_records(path)


def _audit_action_records(
    action_plan_records: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    *,
    lookahead_days: int,
) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for plan in action_plan_records:
        action_date = str(plan.get("action_date", plan.get("date", "")) or "")[:10]
        for action in list(plan.get("actions", []) or []):
            item = _audit_one_action(action, action_date, trade_records, lookahead_days=lookahead_days)
            item["plan_status"] = str(plan.get("status", "") or "")
            item["plan_created_at"] = str(plan.get("created_at", "") or "")
            audits.append(item)
    return audits


def _audit_one_action(
    action: dict[str, Any],
    action_date: str,
    trade_records: list[dict[str, Any]],
    *,
    lookahead_days: int,
) -> dict[str, Any]:
    symbol = str(action.get("symbol", "") or "").zfill(6)
    action_name = str(action.get("action", "") or "")
    required_quantity = _required_quantity(action)
    reference_price = _float_or_none(action.get("market_price"))
    trades = _matching_sell_trades(trade_records, symbol=symbol, action_date=action_date, lookahead_days=lookahead_days)
    executed_quantity = sum(int(trade.get("quantity", 0) or 0) for trade in trades)
    avg_trade_price = _weighted_avg_price(trades)
    delay_days = _delay_days(action_date, trades[0]) if trades else None
    status = _execution_status(action_name, required_quantity, executed_quantity)
    price_deviation_pct = None
    if reference_price not in (None, 0) and avg_trade_price is not None:
        price_deviation_pct = avg_trade_price / reference_price - 1.0
    return {
        "action_date": action_date,
        "symbol": symbol,
        "name": str(action.get("name", "") or ""),
        "action": action_name,
        "reason": str(action.get("reason", "") or ""),
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


def _matching_sell_trades(
    trade_records: list[dict[str, Any]],
    *,
    symbol: str,
    action_date: str,
    lookahead_days: int,
) -> list[dict[str, Any]]:
    start = _parse_date(action_date)
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


def _required_quantity(action: dict[str, Any]) -> int:
    delta = action.get("quantity_delta")
    if delta not in (None, ""):
        return abs(int(delta))
    current = int(action.get("current_quantity", 0) or 0)
    target = action.get("target_quantity")
    if target not in (None, ""):
        return max(current - int(target), 0)
    return current if str(action.get("action", "") or "") == "exit" else 0


def _execution_status(action: str, required_quantity: int, executed_quantity: int) -> str:
    if action not in {"exit", "reduce"}:
        return "not_required"
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


def _delay_days(action_date: str, trade: dict[str, Any]) -> int | None:
    start = _parse_date(action_date)
    end = _parse_date(str(trade.get("date", trade.get("trade_date", "")) or "")[:10])
    if start is None or end is None:
        return None
    return (end - start).days


def _parse_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _action_items(
    actionable_count: int,
    executed_count: int,
    partial_count: int,
    missed_count: int,
    deviations: list[float],
) -> list[str]:
    items: list[str] = []
    if missed_count:
        items.append(f"{missed_count} 个减仓/止损动作没有对应卖出记录，下一次开仓前必须先复核。")
    if partial_count:
        items.append(f"{partial_count} 个动作只部分执行，确认剩余数量是否仍需处理。")
    if actionable_count and executed_count == actionable_count:
        items.append("所有可执行持仓动作都有成交闭环，继续保持动作记录和成交日志同步。")
    if deviations and abs(sum(deviations) / len(deviations)) >= 0.03:
        items.append("动作执行价格偏差超过 3%，复盘是否存在犹豫、追价或流动性问题。")
    if not items:
        items.append("暂无明显动作执行问题。")
    return items
