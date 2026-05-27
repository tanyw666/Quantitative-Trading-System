from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Position:
    symbol: str
    name: str
    quantity: int
    avg_cost: float
    market_price: float | None
    market_value: float | None
    cost_value: float
    unrealized_pnl: float | None
    unrealized_return: float | None
    exposure_pct: float | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PositionBook:
    cash: float
    total_cost: float
    total_market_value: float
    total_unrealized_pnl: float
    total_exposure_pct: float
    positions: list[Position]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["positions"] = [position.to_dict() for position in self.positions]
        return data


def build_position_book(records: list[dict], cash: float, prices: dict[str, float] | None = None) -> PositionBook:
    prices = {str(key).zfill(6): value for key, value in (prices or {}).items()}
    lots: dict[str, list[dict]] = {}
    names: dict[str, str] = {}

    for record in records:
        symbol = str(record.get("symbol", "")).zfill(6)
        if not symbol:
            continue
        names[symbol] = str(record.get("name", "") or names.get(symbol, ""))
        side = str(record.get("side", "")).upper()
        price = float(record.get("price", 0.0))
        quantity = int(record.get("quantity", 0))
        if side == "BUY":
            lots.setdefault(symbol, []).append({"quantity": quantity, "price": price})
        elif side == "SELL":
            _consume_lots(lots.setdefault(symbol, []), quantity)

    positions: list[Position] = []
    total_cost = 0.0
    total_market_value = 0.0
    total_unrealized_pnl = 0.0
    for symbol, symbol_lots in lots.items():
        quantity = sum(int(lot["quantity"]) for lot in symbol_lots)
        if quantity <= 0:
            continue
        cost_value = sum(float(lot["price"]) * int(lot["quantity"]) for lot in symbol_lots)
        avg_cost = cost_value / quantity
        market_price = prices.get(symbol)
        market_value = market_price * quantity if market_price is not None else None
        unrealized_pnl = market_value - cost_value if market_value is not None else None
        unrealized_return = unrealized_pnl / cost_value if unrealized_pnl is not None and cost_value else None
        total_cost += cost_value
        if market_value is not None:
            total_market_value += market_value
            total_unrealized_pnl += unrealized_pnl or 0.0
        positions.append(
            Position(
                symbol=symbol,
                name=names.get(symbol, ""),
                quantity=quantity,
                avg_cost=avg_cost,
                market_price=market_price,
                market_value=market_value,
                cost_value=cost_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_return=unrealized_return,
                exposure_pct=(market_value / cash) if market_value is not None and cash else None,
            )
        )

    total_exposure_pct = total_market_value / cash if cash else 0.0
    return PositionBook(
        cash=cash,
        total_cost=total_cost,
        total_market_value=total_market_value,
        total_unrealized_pnl=total_unrealized_pnl,
        total_exposure_pct=total_exposure_pct,
        positions=sorted(positions, key=lambda item: item.symbol),
    )


def _consume_lots(lots: list[dict], quantity: int) -> None:
    remaining = quantity
    while remaining > 0 and lots:
        lot_quantity = int(lots[0]["quantity"])
        matched = min(remaining, lot_quantity)
        lots[0]["quantity"] = lot_quantity - matched
        remaining -= matched
        if lots[0]["quantity"] <= 0:
            lots.pop(0)
