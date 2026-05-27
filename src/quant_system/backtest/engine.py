from __future__ import annotations

from dataclasses import dataclass

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
    buy_price_field: str = "close"


class BacktestEngine:
    def __init__(self, config: BacktestConfig | None = None, recorder: DecisionRecorder | None = None) -> None:
        self.config = config or BacktestConfig()
        self.recorder = recorder or DecisionRecorder()

    def run(self, frame: pd.DataFrame, strategy) -> BacktestResult:
        data = strategy.generate_signals(frame).sort_values("date").reset_index(drop=True)
        if "symbol" not in data.columns:
            data["symbol"] = "SINGLE"

        cash = self.config.initial_cash
        positions: dict[str, dict[str, float]] = {}
        trades: list[Trade] = []
        equity_rows: list[dict[str, float | pd.Timestamp]] = []
        previous_close: dict[str, float] = {}

        for date, day in data.groupby("date", sort=True):
            day = day.sort_values("symbol")

            for row in day.itertuples(index=False):
                symbol = str(row.symbol)
                close = float(row.close)
                pos = positions.get(symbol)
                should_sell = bool(getattr(row, "sell_signal", False))
                stop_hit = bool(pos and close <= pos["entry_price"] * (1 - self.config.stop_loss_pct))
                if pos and (should_sell or stop_hit):
                    if self.config.enforce_t1 and pd.Timestamp(date) <= pd.Timestamp(pos["entry_date"]):
                        self._record(date, symbol, "exit", "SELL", False, "T+1 blocks same-day sell", {"close": close})
                        continue
                    if self._is_limit_down(symbol, close, previous_close):
                        self._record(date, symbol, "exit", "SELL", False, "Limit-down blocks sell", {"close": close})
                        continue
                    quantity = int(pos["quantity"])
                    price = close * (1 - self.config.slippage_rate)
                    fee = price * quantity * (self.config.commission_rate + self.config.stamp_tax_rate)
                    cash += price * quantity - fee
                    reason = "signal" if should_sell else "stop_loss"
                    trades.append(Trade(date, symbol, "SELL", price, quantity, fee, reason))
                    self._record(date, symbol, "exit", "SELL", True, reason, {"price": price, "quantity": quantity, "fee": fee})
                    del positions[symbol]

            for row in day.itertuples(index=False):
                symbol = str(row.symbol)
                if symbol in positions or not bool(getattr(row, "buy_signal", False)):
                    continue

                close = float(row.close)
                buy_basis = self._row_price(row, self.config.buy_price_field)
                if self._is_limit_up(symbol, buy_basis, previous_close):
                    self._record(
                        date,
                        symbol,
                        "entry",
                        "BUY",
                        False,
                        "Limit-up blocks buy",
                        {"price": buy_basis, "price_field": self.config.buy_price_field},
                    )
                    continue
                price = buy_basis * (1 + self.config.slippage_rate)
                budget = self.config.initial_cash * self.config.max_position_pct
                affordable = min(cash, budget)
                quantity = int(affordable // (price * self.config.lot_size)) * self.config.lot_size
                if quantity <= 0:
                    self._record(date, symbol, "entry", "BUY", False, "Insufficient cash for one lot", {"cash": cash, "price": price})
                    continue

                fee = price * quantity * self.config.commission_rate
                cost = price * quantity + fee
                if cost > cash:
                    self._record(date, symbol, "entry", "BUY", False, "Cash cannot cover fee-adjusted cost", {"cash": cash, "cost": cost})
                    continue
                cash -= cost
                positions[symbol] = {"quantity": float(quantity), "entry_price": price, "entry_date": pd.Timestamp(date)}
                trades.append(Trade(date, symbol, "BUY", price, quantity, fee, "buy_signal"))
                self._record(
                    date,
                    symbol,
                    "entry",
                    "BUY",
                    True,
                    "buy_signal",
                    {"price": price, "quantity": quantity, "fee": fee, "price_field": self.config.buy_price_field},
                )

            mark_to_market = 0.0
            latest_prices = {str(row.symbol): float(row.close) for row in day.itertuples(index=False)}
            for symbol, pos in positions.items():
                mark_to_market += pos["quantity"] * latest_prices.get(symbol, pos["entry_price"])
            equity_rows.append({"date": date, "cash": cash, "market_value": mark_to_market, "equity": cash + mark_to_market})
            previous_close.update(latest_prices)

        equity_curve = pd.DataFrame(equity_rows)
        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            initial_cash=self.config.initial_cash,
            final_cash=cash,
        )

    def _is_limit_up(self, symbol: str, close: float, previous_close: dict[str, float]) -> bool:
        prev = previous_close.get(symbol)
        return bool(prev and close >= prev * (1 + self.config.limit_pct) * 0.999)

    def _is_limit_down(self, symbol: str, close: float, previous_close: dict[str, float]) -> bool:
        prev = previous_close.get(symbol)
        return bool(prev and close <= prev * (1 - self.config.limit_pct) * 1.001)

    def _row_price(self, row, field: str) -> float:
        if field not in {"open", "close"}:
            raise ValueError(f"Unsupported buy price field: {field}")
        return float(getattr(row, field))

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
