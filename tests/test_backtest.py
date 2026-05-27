import pandas as pd

from quant_system.backtest.engine import BacktestConfig, BacktestEngine
from quant_system.trace.events import DecisionRecorder


class BuyAndHoldStrategy:
    name = "buy_and_hold"

    def generate_signals(self, frame):
        data = frame.copy()
        data["buy_signal"] = data.index == 0
        data["sell_signal"] = False
        return data

    def screen(self, frame):
        return frame.head(0)


def test_backtest_buys_lot_and_marks_equity():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=3),
            "open": [10, 11, 12],
            "high": [10, 11, 12],
            "low": [10, 11, 12],
            "close": [10, 11, 12],
            "volume": [1000, 1000, 1000],
        }
    )
    engine = BacktestEngine(BacktestConfig(initial_cash=10000, max_position_pct=1.0, commission_rate=0, slippage_rate=0))
    result = engine.run(frame, BuyAndHoldStrategy())

    assert len(result.trades) == 1
    assert result.trades[0].quantity == 1000
    assert result.summary()["final_equity"] == 12000


class BuyThenSellStrategy:
    name = "buy_then_sell"

    def generate_signals(self, frame):
        data = frame.copy()
        data["buy_signal"] = data.index == 0
        data["sell_signal"] = data.index == 0
        return data

    def screen(self, frame):
        return frame.head(0)


def test_backtest_records_t1_block():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=2),
            "open": [10, 11],
            "high": [10, 11],
            "low": [10, 11],
            "close": [10, 11],
            "volume": [1000, 1000],
        }
    )
    recorder = DecisionRecorder()
    engine = BacktestEngine(
        BacktestConfig(initial_cash=10000, max_position_pct=1.0, commission_rate=0, slippage_rate=0),
        recorder=recorder,
    )
    result = engine.run(frame, BuyThenSellStrategy())

    assert len(result.trades) == 1
    assert result.trades[0].side == "BUY"
    assert all(event.action != "SELL" for event in recorder.events)


class BuyOnSecondDayStrategy:
    name = "buy_on_second_day"

    def generate_signals(self, frame):
        data = frame.copy()
        data["buy_signal"] = data.index == 1
        data["sell_signal"] = False
        return data

    def screen(self, frame):
        return frame.head(0)


def test_backtest_records_limit_up_block():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=2),
            "symbol": ["AAA", "AAA"],
            "open": [10, 11],
            "high": [10, 11],
            "low": [10, 11],
            "close": [10, 11],
            "volume": [1000, 1000],
        }
    )
    recorder = DecisionRecorder()
    engine = BacktestEngine(
        BacktestConfig(initial_cash=10000, max_position_pct=0.1, commission_rate=0, slippage_rate=0),
        recorder=recorder,
    )
    engine.run(frame, BuyOnSecondDayStrategy())

    assert any(event.reason == "Limit-up blocks buy" for event in recorder.events)


def test_backtest_can_buy_at_open_price():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=2),
            "open": [9, 11],
            "high": [10, 12],
            "low": [9, 11],
            "close": [10, 12],
            "volume": [1000, 1000],
        }
    )
    engine = BacktestEngine(
        BacktestConfig(
            initial_cash=10000,
            max_position_pct=1.0,
            commission_rate=0,
            slippage_rate=0,
            buy_price_field="open",
        )
    )
    result = engine.run(frame, BuyAndHoldStrategy())

    assert result.trades[0].price == 9
