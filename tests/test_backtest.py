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


class BuyThenSellStrategy:
    name = "buy_then_sell"

    def generate_signals(self, frame):
        data = frame.copy()
        data["buy_signal"] = data.index == 0
        data["sell_signal"] = data.index == 0
        return data

    def screen(self, frame):
        return frame.head(0)


class BuyOnSecondDayStrategy:
    name = "buy_on_second_day"

    def generate_signals(self, frame):
        data = frame.copy()
        data["buy_signal"] = data.index == 1
        data["sell_signal"] = False
        return data

    def screen(self, frame):
        return frame.head(0)


def sample_frame(**overrides):
    payload = {
        "date": pd.date_range("2024-01-01", periods=3),
        "symbol": ["AAA", "AAA", "AAA"],
        "open": [10, 11, 12],
        "high": [10, 11, 12],
        "low": [10, 11, 12],
        "close": [10, 11, 12],
        "volume": [1000, 1000, 1000],
    }
    payload.update(overrides)
    return pd.DataFrame(payload)


def test_backtest_executes_signal_on_next_bar_and_marks_equity():
    frame = sample_frame(open=[10, 10.5, 12])
    engine = BacktestEngine(BacktestConfig(initial_cash=10000, max_position_pct=1.0, commission_rate=0, slippage_rate=0))
    result = engine.run(frame, BuyAndHoldStrategy())

    assert len(result.trades) == 1
    assert result.trades[0].date == pd.Timestamp("2024-01-02")
    assert result.trades[0].signal_date == pd.Timestamp("2024-01-01")
    assert result.trades[0].price == 10.5
    assert result.trades[0].quantity == 900
    assert result.summary()["final_equity"] == 11350


def test_backtest_records_t1_block_for_same_bar_execution():
    frame = sample_frame(date=pd.date_range("2024-01-01", periods=3), close=[10, 11, 12])
    recorder = DecisionRecorder()
    engine = BacktestEngine(
        BacktestConfig(
            initial_cash=10000,
            max_position_pct=1.0,
            commission_rate=0,
            slippage_rate=0,
            execution_timing="same_bar",
        ),
        recorder=recorder,
    )
    result = engine.run(frame, BuyThenSellStrategy())

    assert [trade.side for trade in result.trades] == ["BUY"]
    assert any(event.reason == "T+1 blocks same-day sell" for event in recorder.events)


def test_backtest_records_limit_up_block_on_execution_bar():
    frame = sample_frame(open=[10, 11, 12], close=[10, 11, 12])
    recorder = DecisionRecorder()
    engine = BacktestEngine(
        BacktestConfig(initial_cash=10000, max_position_pct=0.1, commission_rate=0, slippage_rate=0),
        recorder=recorder,
    )
    engine.run(frame, BuyAndHoldStrategy())

    assert any(event.reason == "Limit-up blocks buy" for event in recorder.events)


def test_backtest_blocks_suspended_execution_bar():
    frame = sample_frame(volume=[1000, 0, 1000])
    recorder = DecisionRecorder()
    engine = BacktestEngine(
        BacktestConfig(initial_cash=10000, max_position_pct=1.0, commission_rate=0, slippage_rate=0),
        recorder=recorder,
    )
    result = engine.run(frame, BuyAndHoldStrategy())

    assert result.trades == []
    assert any(event.reason == "Suspended or invalid bar blocks buy" for event in recorder.events)


def test_backtest_can_use_legacy_same_bar_close_price():
    frame = sample_frame(open=[9, 11, 12], close=[10, 12, 13])
    engine = BacktestEngine(
        BacktestConfig(
            initial_cash=10000,
            max_position_pct=1.0,
            commission_rate=0,
            slippage_rate=0,
            buy_price_field="close",
            execution_timing="same_bar",
        )
    )
    result = engine.run(frame, BuyAndHoldStrategy())

    assert result.trades[0].price == 10


def test_backtest_records_unfilled_signal_without_next_bar():
    frame = sample_frame(date=[pd.Timestamp("2024-01-01")], symbol=["AAA"], open=[10], high=[10], low=[10], close=[10], volume=[1000])
    recorder = DecisionRecorder()
    engine = BacktestEngine(
        BacktestConfig(initial_cash=10000, max_position_pct=1.0, commission_rate=0, slippage_rate=0),
        recorder=recorder,
    )
    engine.run(frame, BuyAndHoldStrategy())

    assert any(event.reason == "No next bar to execute signal" for event in recorder.events)
