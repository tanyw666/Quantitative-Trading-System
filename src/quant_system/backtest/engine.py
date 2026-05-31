from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from quant_system.backtest.models import BacktestResult, Trade
from quant_system.trace.events import DecisionEvent, DecisionRecorder


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100000.0
    commission_rate: float = 0.0003
    stamp_tax_rate: float = 0.001
    slippage_rate: float = 0.0005
    max_position_pct: float = 0.2
    stop_loss_pct: float = 0.08
    lot_size: int = 100
    limit_pct: float = 0.10
    enforce_t1: bool = True
    buy_price_field: str = "open"
    sell_price_field: str | None = None
    execution_timing: str = "next_bar"


@dataclass(frozen=True)
class PendingOrder:
    signal_date: pd.Timestamp
    symbol: str
    side: str
    reason: str
    stage: str


class BacktestEngine:
    def __init__(self, config: BacktestConfig | None = None, recorder: DecisionRecorder | None = None) -> None:
        self.config = config or BacktestConfig()
        self.recorder = recorder or DecisionRecorder()
        self._validate_config()

    def run(self, frame: pd.DataFrame, strategy) -> BacktestResult:
        data = strategy.generate_signals(frame).sort_values("date").reset_index(drop=True)
        if "symbol" not in data.columns:
            data["symbol"] = "SINGLE"
        data["date"] = pd.to_datetime(data["date"])

        cash = self.config.initial_cash
        positions: dict[str, dict[str, float]] = {}
        trades: list[Trade] = []
        equity_rows: list[dict[str, float | pd.Timestamp]] = []
        previous_close: dict[str, float] = {}
        pending_orders: dict[str, list[PendingOrder]] = {}

        for date, day in data.groupby("date", sort=True):
            day = day.sort_values("symbol")

            for row in day.itertuples(index=False):
                symbol = str(row.symbol)
                cash = self._execute_pending_orders(
                    row,
                    pd.Timestamp(date),
                    pending_orders,
                    positions,
                    trades,
                    cash,
                    previous_close,
                )

            for row in day.itertuples(index=False):
                symbol = str(row.symbol)
                if symbol not in positions and bool(getattr(row, "buy_signal", False)):
                    order = PendingOrder(pd.Timestamp(date), symbol, "BUY", "buy_signal", "entry")
                    cash = self._handle_order_signal(row, order, pending_orders, positions, trades, cash, previous_close)

                close = float(row.close)
                pos = positions.get(symbol)
                should_sell = bool(getattr(row, "sell_signal", False))
                stop_hit = bool(pos and close <= pos["entry_price"] * (1 - self.config.stop_loss_pct))
                if pos and (should_sell or stop_hit):
                    reason = "signal" if should_sell else "stop_loss"
                    order = PendingOrder(pd.Timestamp(date), symbol, "SELL", reason, "exit")
                    cash = self._handle_order_signal(row, order, pending_orders, positions, trades, cash, previous_close)

            mark_to_market = 0.0
            latest_prices = {str(row.symbol): float(row.close) for row in day.itertuples(index=False)}
            for symbol, pos in positions.items():
                mark_to_market += pos["quantity"] * latest_prices.get(symbol, pos["entry_price"])
            equity_rows.append({"date": date, "cash": cash, "market_value": mark_to_market, "equity": cash + mark_to_market})
            previous_close.update(latest_prices)

        self._record_unfilled_pending_orders(pending_orders)
        equity_curve = pd.DataFrame(equity_rows)
        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            initial_cash=self.config.initial_cash,
            final_cash=cash,
        )

    def _handle_order_signal(
        self,
        row,
        order: PendingOrder,
        pending_orders: dict[str, list[PendingOrder]],
        positions: dict[str, dict[str, float]],
        trades: list[Trade],
        cash: float,
        previous_close: dict[str, float],
    ) -> float:
        if self.config.execution_timing == "same_bar":
            return self._execute_order(row, order.signal_date, order, positions, trades, cash, previous_close)

        if self._has_pending_side(pending_orders, order.symbol, order.side):
            self._record(
                order.signal_date,
                order.symbol,
                order.stage,
                order.side,
                False,
                "Existing pending order blocks duplicate signal",
                {"reason": order.reason},
            )
            return cash

        pending_orders.setdefault(order.symbol, []).append(order)
        self._record(
            order.signal_date,
            order.symbol,
            f"{order.stage}_signal",
            order.side,
            True,
            "Signal queued for next bar execution",
            {"reason": order.reason, "execution_timing": self.config.execution_timing},
        )
        return cash

    def _execute_pending_orders(
        self,
        row,
        date: pd.Timestamp,
        pending_orders: dict[str, list[PendingOrder]],
        positions: dict[str, dict[str, float]],
        trades: list[Trade],
        cash: float,
        previous_close: dict[str, float],
    ) -> float:
        symbol = str(row.symbol)
        orders = pending_orders.pop(symbol, [])
        future_orders: list[PendingOrder] = []
        for order in orders:
            if date <= order.signal_date:
                future_orders.append(order)
                continue
            cash = self._execute_order(row, date, order, positions, trades, cash, previous_close)
        if future_orders:
            pending_orders[symbol] = future_orders
        return cash

    def _execute_order(
        self,
        row,
        execution_date: pd.Timestamp,
        order: PendingOrder,
        positions: dict[str, dict[str, float]],
        trades: list[Trade],
        cash: float,
        previous_close: dict[str, float],
    ) -> float:
        if order.side == "BUY":
            return self._execute_buy(row, execution_date, order, positions, trades, cash, previous_close)
        if order.side == "SELL":
            return self._execute_sell(row, execution_date, order, positions, trades, cash, previous_close)
        raise ValueError(f"Unsupported order side: {order.side}")

    def _execute_sell(
        self,
        row,
        execution_date: pd.Timestamp,
        order: PendingOrder,
        positions: dict[str, dict[str, float]],
        trades: list[Trade],
        cash: float,
        previous_close: dict[str, float],
    ) -> float:
        symbol = order.symbol
        pos = positions.get(symbol)
        price_field = self._sell_price_field()
        basis = self._row_price(row, price_field)
        if not pos:
            self._record(execution_date, symbol, "exit", "SELL", False, "No open position at execution", {"signal_date": order.signal_date})
            return cash
        if self.config.enforce_t1 and execution_date <= pd.Timestamp(pos["entry_date"]):
            self._record(execution_date, symbol, "exit", "SELL", False, "T+1 blocks same-day sell", {"signal_date": order.signal_date})
            return cash
        if self._is_untradable(row, price_field):
            self._record(execution_date, symbol, "exit", "SELL", False, "Suspended or invalid bar blocks sell", {"signal_date": order.signal_date})
            return cash
        if self._is_limit_down(symbol, basis, previous_close):
            self._record(execution_date, symbol, "exit", "SELL", False, "Limit-down blocks sell", {"price": basis, "price_field": price_field})
            return cash

        quantity = int(pos["quantity"])
        price = basis * (1 - self.config.slippage_rate)
        fee = price * quantity * (self.config.commission_rate + self.config.stamp_tax_rate)
        cash += price * quantity - fee
        trades.append(Trade(execution_date, symbol, "SELL", price, quantity, fee, order.reason, order.signal_date, price_field))
        self._record(
            execution_date,
            symbol,
            "exit",
            "SELL",
            True,
            order.reason,
            {"price": price, "quantity": quantity, "fee": fee, "signal_date": order.signal_date, "price_field": price_field},
        )
        del positions[symbol]
        return cash

    def _execute_buy(
        self,
        row,
        execution_date: pd.Timestamp,
        order: PendingOrder,
        positions: dict[str, dict[str, float]],
        trades: list[Trade],
        cash: float,
        previous_close: dict[str, float],
    ) -> float:
        symbol = order.symbol
        if symbol in positions:
            self._record(execution_date, symbol, "entry", "BUY", False, "Existing position blocks buy", {"signal_date": order.signal_date})
            return cash

        price_field = self.config.buy_price_field
        basis = self._row_price(row, price_field)
        if self._is_untradable(row, price_field):
            self._record(execution_date, symbol, "entry", "BUY", False, "Suspended or invalid bar blocks buy", {"signal_date": order.signal_date})
            return cash
        if self._is_limit_up(symbol, basis, previous_close):
            self._record(
                execution_date,
                symbol,
                "entry",
                "BUY",
                False,
                "Limit-up blocks buy",
                {"price": basis, "price_field": price_field, "signal_date": order.signal_date},
            )
            return cash

        price = basis * (1 + self.config.slippage_rate)
        budget = self.config.initial_cash * self.config.max_position_pct
        affordable = min(cash, budget)
        quantity = int(affordable // (price * self.config.lot_size)) * self.config.lot_size
        if quantity <= 0:
            self._record(execution_date, symbol, "entry", "BUY", False, "Insufficient cash for one lot", {"cash": cash, "price": price})
            return cash

        fee = price * quantity * self.config.commission_rate
        cost = price * quantity + fee
        if cost > cash:
            self._record(execution_date, symbol, "entry", "BUY", False, "Cash cannot cover fee-adjusted cost", {"cash": cash, "cost": cost})
            return cash
        cash -= cost
        positions[symbol] = {"quantity": float(quantity), "entry_price": price, "entry_date": execution_date}
        trades.append(Trade(execution_date, symbol, "BUY", price, quantity, fee, order.reason, order.signal_date, price_field))
        self._record(
            execution_date,
            symbol,
            "entry",
            "BUY",
            True,
            order.reason,
            {"price": price, "quantity": quantity, "fee": fee, "price_field": price_field, "signal_date": order.signal_date},
        )
        return cash

    def _is_limit_up(self, symbol: str, close: float, previous_close: dict[str, float]) -> bool:
        prev = previous_close.get(symbol)
        return bool(prev and close >= prev * (1 + self.config.limit_pct) * 0.999)

    def _is_limit_down(self, symbol: str, close: float, previous_close: dict[str, float]) -> bool:
        prev = previous_close.get(symbol)
        return bool(prev and close <= prev * (1 - self.config.limit_pct) * 1.001)

    def _row_price(self, row, field: str) -> float:
        if field not in {"open", "close"}:
            raise ValueError(f"Unsupported price field: {field}")
        return float(getattr(row, field))

    def _sell_price_field(self) -> str:
        return self.config.sell_price_field or self.config.buy_price_field

    def _is_untradable(self, row, price_field: str) -> bool:
        price = self._row_price(row, price_field)
        close = float(getattr(row, "close"))
        volume = float(getattr(row, "volume", 0.0) or 0.0)
        return bool(
            volume <= 0
            or not math.isfinite(price)
            or not math.isfinite(close)
            or price <= 0
            or close <= 0
        )

    def _has_pending_side(self, pending_orders: dict[str, list[PendingOrder]], symbol: str, side: str) -> bool:
        return any(order.side == side for order in pending_orders.get(symbol, []))

    def _record_unfilled_pending_orders(self, pending_orders: dict[str, list[PendingOrder]]) -> None:
        for symbol, orders in pending_orders.items():
            for order in orders:
                self._record(
                    order.signal_date,
                    symbol,
                    order.stage,
                    order.side,
                    False,
                    "No next bar to execute signal",
                    {"reason": order.reason, "execution_timing": self.config.execution_timing},
                )

    def _validate_config(self) -> None:
        if self.config.execution_timing not in {"same_bar", "next_bar"}:
            raise ValueError(f"Unsupported execution timing: {self.config.execution_timing}")
        self._validate_price_field(self.config.buy_price_field)
        if self.config.sell_price_field is not None:
            self._validate_price_field(self.config.sell_price_field)

    def _validate_price_field(self, field: str) -> None:
        if field not in {"open", "close"}:
            raise ValueError(f"Unsupported price field: {field}")

    def _record(
        self,
        date: pd.Timestamp,
        symbol: str,
        stage: str,
        action: str,
        passed: bool,
        reason: str,
        details: dict,
    ) -> None:
        self.recorder.record(
            DecisionEvent.from_timestamp(
                pd.Timestamp(date),
                symbol=symbol,
                stage=stage,
                action=action,
                passed=passed,
                reason=reason,
                details=details,
            )
        )
