from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from quant_system.storage.jsonl import append_jsonl, read_jsonl


@dataclass(frozen=True)
class OpenLot:
    lot_id: str
    symbol: str
    name: str
    entry_date: str
    entry_price: float
    original_quantity: int
    remaining_quantity: int
    cost_value: float
    market_price: float | None
    market_value: float | None
    unrealized_pnl: float | None
    unrealized_return: float | None
    holding_days: int | None
    age_bucket: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClosedLot:
    lot_id: str
    symbol: str
    name: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    realized_pnl: float
    realized_return: float
    holding_days: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LotBook:
    created_at: str
    as_of: str
    total_open_lots: int
    total_closed_lots: int
    open_quantity: int
    open_cost_value: float
    open_market_value: float
    open_unrealized_pnl: float
    realized_pnl: float
    open_lots: list[OpenLot]
    closed_lots: list[ClosedLot]
    summary: dict[str, Any]
    action_items: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["open_lots"] = [item.to_dict() for item in self.open_lots]
        data["closed_lots"] = [item.to_dict() for item in self.closed_lots]
        return data


def build_lot_book(
    trade_records: list[dict[str, Any]],
    *,
    prices: dict[str, float] | None = None,
    as_of: str | None = None,
) -> LotBook:
    prices = {str(key).zfill(6): float(value) for key, value in (prices or {}).items()}
    current_date = _parse_date(as_of) or date.today()
    raw_lots: dict[str, list[dict[str, Any]]] = {}
    closed_lots: list[ClosedLot] = []
    names: dict[str, str] = {}
    sequence = 0

    for record in _ordered_records(trade_records):
        symbol = str(record.get("symbol", "") or "").zfill(6)
        if not symbol:
            continue
        side = str(record.get("side", "") or "").upper()
        trade_date = str(record.get("date", record.get("trade_date", "")) or "")[:10]
        price = float(record.get("price", 0) or 0)
        quantity = int(record.get("quantity", 0) or 0)
        name = str(record.get("name", "") or names.get(symbol, "") or "")
        names[symbol] = name
        if quantity <= 0:
            continue
        if side == "BUY":
            sequence += 1
            raw_lots.setdefault(symbol, []).append(
                {
                    "lot_id": f"{symbol}-{trade_date or 'unknown'}-{sequence}",
                    "symbol": symbol,
                    "name": name,
                    "entry_date": trade_date,
                    "entry_price": price,
                    "original_quantity": quantity,
                    "remaining_quantity": quantity,
                }
            )
        elif side == "SELL":
            closed_lots.extend(_consume_lots(raw_lots.setdefault(symbol, []), record, name=name))

    open_lots = [_open_lot(lot, prices=prices, as_of=current_date) for lots in raw_lots.values() for lot in lots if int(lot["remaining_quantity"]) > 0]
    open_lots = sorted(open_lots, key=lambda item: (item.symbol, item.entry_date, item.lot_id))
    closed_lots = sorted(closed_lots, key=lambda item: (item.exit_date, item.symbol, item.lot_id))
    open_cost_value = round(sum(item.cost_value for item in open_lots), 2)
    open_market_value = round(sum(float(item.market_value or 0.0) for item in open_lots), 2)
    open_unrealized_pnl = round(sum(float(item.unrealized_pnl or 0.0) for item in open_lots), 2)
    realized_pnl = round(sum(item.realized_pnl for item in closed_lots), 2)
    summary = summarize_lot_lifecycle(open_lots=open_lots, closed_lots=closed_lots)
    return LotBook(
        created_at=datetime.now(timezone.utc).isoformat(),
        as_of=current_date.isoformat(),
        total_open_lots=len(open_lots),
        total_closed_lots=len(closed_lots),
        open_quantity=sum(item.remaining_quantity for item in open_lots),
        open_cost_value=open_cost_value,
        open_market_value=open_market_value,
        open_unrealized_pnl=open_unrealized_pnl,
        realized_pnl=realized_pnl,
        open_lots=open_lots,
        closed_lots=closed_lots,
        summary=summary,
        action_items=_action_items(summary),
    )


def summarize_lot_lifecycle(*, open_lots: list[OpenLot], closed_lots: list[ClosedLot]) -> dict[str, Any]:
    age_counts: dict[str, int] = {}
    for lot in open_lots:
        age_counts[lot.age_bucket] = age_counts.get(lot.age_bucket, 0) + 1
    winners = [lot for lot in closed_lots if lot.realized_pnl > 0]
    losers = [lot for lot in closed_lots if lot.realized_pnl < 0]
    closed_days = [lot.holding_days for lot in closed_lots if lot.holding_days is not None]
    open_days = [lot.holding_days for lot in open_lots if lot.holding_days is not None]
    stale_open = [lot for lot in open_lots if (lot.holding_days or 0) >= 20 and (lot.unrealized_return or 0.0) <= 0]
    return {
        "open_lot_count": len(open_lots),
        "closed_lot_count": len(closed_lots),
        "age_counts": age_counts,
        "realized_win_count": len(winners),
        "realized_loss_count": len(losers),
        "realized_win_rate": len(winners) / len(closed_lots) if closed_lots else 0.0,
        "avg_closed_holding_days": sum(closed_days) / len(closed_days) if closed_days else 0.0,
        "avg_open_holding_days": sum(open_days) / len(open_days) if open_days else 0.0,
        "stale_open_lot_count": len(stale_open),
        "largest_open_lot": _largest_open_lot(open_lots),
    }


def render_lot_book_lines(book: dict[str, Any] | LotBook | None, *, limit: int = 10) -> list[str]:
    payload = book.to_dict() if isinstance(book, LotBook) else (book or {})
    if not payload:
        return ["- No lot lifecycle snapshot available."]
    summary = payload.get("summary", {}) or {}
    lines = [
        f"- Open lots: {int(payload.get('total_open_lots', 0) or 0)}",
        f"- Closed lots: {int(payload.get('total_closed_lots', 0) or 0)}",
        f"- Open market value: {float(payload.get('open_market_value', 0) or 0):.2f}",
        f"- Open unrealized PnL: {float(payload.get('open_unrealized_pnl', 0) or 0):.2f}",
        f"- Realized PnL: {float(payload.get('realized_pnl', 0) or 0):.2f}",
        f"- Realized win rate: {float(summary.get('realized_win_rate', 0) or 0):.1%}",
    ]
    open_lots = list(payload.get("open_lots", []) or [])
    if open_lots:
        lines.extend(["", "| Lot | Symbol | Entry | Qty | Cost | Price | PnL | Days |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"])
        for lot in open_lots[: max(int(limit), 0)]:
            market_price = lot.get("market_price")
            holding_days = lot.get("holding_days")
            unrealized_pnl = lot.get("unrealized_pnl")
            price_text = "" if market_price is None else f"{float(market_price):.2f}"
            pnl_text = "" if unrealized_pnl is None else f"{float(unrealized_pnl or 0):.2f}"
            lines.append(
                f"| {lot.get('lot_id', '')} | {lot.get('symbol', '')} | {lot.get('entry_date', '')} | "
                f"{int(lot.get('remaining_quantity', 0) or 0)} | {float(lot.get('entry_price', 0) or 0):.2f} | "
                f"{price_text} | {pnl_text} | "
                f"{'' if holding_days is None else int(holding_days)} |"
            )
    action_items = list(payload.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "Action items:"])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def render_lot_book_markdown(book: dict[str, Any] | LotBook | None) -> str:
    return "\n".join(["# Lot Lifecycle", "", *render_lot_book_lines(book), ""])


def append_lot_book_record(path: Path, book: LotBook | dict[str, Any]) -> None:
    payload = book.to_dict() if isinstance(book, LotBook) else dict(book)
    append_jsonl(path, payload)


def read_lot_book_records(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def _consume_lots(lots: list[dict[str, Any]], sell_record: dict[str, Any], *, name: str) -> list[ClosedLot]:
    remaining = int(sell_record.get("quantity", 0) or 0)
    exit_price = float(sell_record.get("price", 0) or 0)
    exit_date = str(sell_record.get("date", sell_record.get("trade_date", "")) or "")[:10]
    reason = str(sell_record.get("reason", "") or "")
    closed: list[ClosedLot] = []
    while remaining > 0 and lots:
        lot = lots[0]
        lot_quantity = int(lot["remaining_quantity"])
        matched = min(remaining, lot_quantity)
        lot["remaining_quantity"] = lot_quantity - matched
        remaining -= matched
        entry_price = float(lot["entry_price"])
        realized_pnl = round((exit_price - entry_price) * matched, 2)
        realized_return = (exit_price / entry_price - 1.0) if entry_price else 0.0
        holding_days = _days_between(str(lot.get("entry_date", "") or ""), exit_date)
        closed.append(
            ClosedLot(
                lot_id=str(lot["lot_id"]),
                symbol=str(lot["symbol"]),
                name=str(lot.get("name", "") or name),
                entry_date=str(lot.get("entry_date", "") or ""),
                exit_date=exit_date,
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=matched,
                realized_pnl=realized_pnl,
                realized_return=realized_return,
                holding_days=holding_days,
                reason=reason,
            )
        )
        if int(lot["remaining_quantity"]) <= 0:
            lots.pop(0)
    return closed


def _open_lot(lot: dict[str, Any], *, prices: dict[str, float], as_of: date) -> OpenLot:
    symbol = str(lot["symbol"])
    remaining_quantity = int(lot["remaining_quantity"])
    entry_price = float(lot["entry_price"])
    market_price = prices.get(symbol)
    cost_value = round(entry_price * remaining_quantity, 2)
    market_value = round(market_price * remaining_quantity, 2) if market_price is not None else None
    unrealized_pnl = round((market_value or 0.0) - cost_value, 2) if market_value is not None else None
    unrealized_return = market_price / entry_price - 1.0 if market_price is not None and entry_price else None
    holding_days = _days_between(str(lot.get("entry_date", "") or ""), as_of.isoformat())
    return OpenLot(
        lot_id=str(lot["lot_id"]),
        symbol=symbol,
        name=str(lot.get("name", "") or ""),
        entry_date=str(lot.get("entry_date", "") or ""),
        entry_price=entry_price,
        original_quantity=int(lot["original_quantity"]),
        remaining_quantity=remaining_quantity,
        cost_value=cost_value,
        market_price=market_price,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_return=unrealized_return,
        holding_days=holding_days,
        age_bucket=_age_bucket(holding_days),
    )


def _ordered_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(enumerate(records), key=lambda item: (str(item[1].get("date", item[1].get("trade_date", "")) or ""), item[0]))
    return [record for _, record in ordered]


def _parse_date(value: str | None) -> date | None:
    try:
        return datetime.fromisoformat(str(value or "")[:10]).date()
    except ValueError:
        return None


def _days_between(start: str, end: str) -> int | None:
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if start_date is None or end_date is None:
        return None
    return (end_date - start_date).days


def _age_bucket(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days <= 5:
        return "short"
    if days <= 20:
        return "normal"
    return "stale"


def _largest_open_lot(open_lots: list[OpenLot]) -> dict[str, Any] | None:
    lots_with_value = [lot for lot in open_lots if lot.market_value is not None]
    if not lots_with_value:
        return None
    lot = sorted(lots_with_value, key=lambda item: float(item.market_value or 0), reverse=True)[0]
    return {"symbol": lot.symbol, "lot_id": lot.lot_id, "market_value": lot.market_value, "holding_days": lot.holding_days}


def _action_items(summary: dict[str, Any]) -> list[str]:
    items: list[str] = []
    stale_count = int(summary.get("stale_open_lot_count", 0) or 0)
    if stale_count:
        items.append(f"{stale_count} open lots are stale and not profitable; review time-stop or thesis validity.")
    largest = summary.get("largest_open_lot") or {}
    if largest:
        items.append(f"Largest open lot is {largest.get('symbol')} ({largest.get('lot_id')}); make sure its stop is current.")
    if float(summary.get("realized_win_rate", 0) or 0) < 0.4 and int(summary.get("closed_lot_count", 0) or 0) >= 5:
        items.append("Realized lot win rate is below 40%; reduce size until entry quality improves.")
    if not items:
        items.append("Lot lifecycle has no obvious warning in the current sample.")
    return items
