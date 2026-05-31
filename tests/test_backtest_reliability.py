import pandas as pd

from quant_system.backtest.models import Trade
from quant_system.backtest.reliability import (
    BacktestReliabilityConfig,
    build_backtest_reliability_audit,
    render_backtest_reliability_markdown,
    summarize_signal_execution_consistency,
)


class FirstDayBuyStrategy:
    name = "first_day_buy"

    def generate_signals(self, frame):
        data = frame.copy().reset_index(drop=True)
        data["buy_signal"] = data.index == 0
        data["sell_signal"] = False
        return data


class NeverBuyStrategy:
    name = "never_buy"

    def generate_signals(self, frame):
        data = frame.copy()
        data["buy_signal"] = False
        data["sell_signal"] = False
        return data


def sample_frame():
    dates = pd.date_range("2024-01-01", periods=12)
    closes = [10, 10.2, 10.5, 10.7, 11.0, 11.3, 11.5, 11.7, 11.8, 12.0, 12.1, 12.2]
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": ["000001"] * len(dates),
            "open": closes,
            "high": [value + 0.2 for value in closes],
            "low": [value - 0.2 for value in closes],
            "close": closes,
            "volume": [1000] * len(dates),
        }
    )


def test_build_backtest_reliability_audit_compares_strategies_and_periods():
    payload = build_backtest_reliability_audit(
        sample_frame(),
        [("buy", FirstDayBuyStrategy()), ("flat", NeverBuyStrategy())],
        BacktestReliabilityConfig(
            initial_cash=10000,
            regime_lookback=3,
            bull_threshold=0.02,
            bear_threshold=-0.02,
            min_rows_per_symbol=2,
        ),
    )

    assert payload["ranking"][0]["strategy"] == "buy"
    assert payload["strategies"][0]["splits"]
    assert payload["strategies"][0]["regimes"]
    assert payload["strategies"][0]["consistency"]["status"] == "pass"


def test_render_backtest_reliability_markdown_contains_key_sections():
    payload = build_backtest_reliability_audit(
        sample_frame(),
        [("buy", FirstDayBuyStrategy())],
        BacktestReliabilityConfig(initial_cash=10000, regime_lookback=3, min_rows_per_symbol=2),
    )

    content = render_backtest_reliability_markdown(payload)

    assert "# 回测可信度审计" in content
    assert "策略横向排名" in content
    assert "分段和成交审计" in content


def test_signal_execution_consistency_blocks_same_bar_fill_in_next_bar_mode():
    trades = [
        Trade(
            date=pd.Timestamp("2024-01-01"),
            symbol="000001",
            side="BUY",
            price=10,
            quantity=100,
            fee=0,
            reason="buy",
            signal_date=pd.Timestamp("2024-01-01"),
        )
    ]

    summary = summarize_signal_execution_consistency(trades, execution_timing="next_bar")

    assert summary["status"] == "block"
    assert summary["future_signal_anomalies"] == 1


def test_backtest_reliability_blocks_failed_data_health():
    frame = sample_frame()
    frame.loc[frame.index[-1], "volume"] = 0

    payload = build_backtest_reliability_audit(
        frame,
        [("buy", FirstDayBuyStrategy())],
        BacktestReliabilityConfig(initial_cash=10000, min_rows_per_symbol=2),
    )

    assert payload["data_health"]["status"] == "fail"
    assert payload["ranking"] == []
    assert payload["strategies"][0]["ok"] is False
