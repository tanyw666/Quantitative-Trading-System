from pathlib import Path

import pandas as pd

from quant_system.factors.technical import add_core_factors
from quant_system.strategies.registry import create_strategy_from_config
from quant_system.strategies.steady_reversal_sharpe import SteadyReversalSharpeStrategy


def _symbol_frame(symbol: str, start: float, step: float, turnover: float, amplitude: float) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=80)
    closes = [start + step * index for index in range(len(dates))]
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": [symbol] * len(dates),
            "name": [symbol] * len(dates),
            "open": [value - amplitude / 4 for value in closes],
            "high": [value + amplitude / 2 for value in closes],
            "low": [value - amplitude / 2 for value in closes],
            "close": closes,
            "volume": [1_000_000] * len(dates),
            "turnover": [turnover] * len(dates),
        }
    )


def _sample_frame() -> pd.DataFrame:
    return pd.concat(
        [
            _symbol_frame("AAA", 20, 0.12, 0.006, 0.20),
            _symbol_frame("BBB", 20, 0.12, 0.030, 1.20),
            _symbol_frame("CCC", 20, -0.03, 0.008, 0.20),
        ],
        ignore_index=True,
    )


def test_core_factors_add_like_sharpe_and_low_attention_reversal_score():
    enriched = add_core_factors(_sample_frame())
    latest = enriched.groupby("symbol").tail(1).set_index("symbol")

    for column in [
        "like_sharpe_10",
        "turnover_60_avg",
        "amplitude_10_avg",
        "low_turnover_z",
        "low_amplitude_z",
        "steady_reversal_score",
    ]:
        assert column in enriched.columns
    assert latest.loc["AAA", "like_sharpe_10"] > 1
    assert latest.loc["AAA", "steady_reversal_score"] > latest.loc["BBB", "steady_reversal_score"]


def test_steady_reversal_sharpe_screen_selects_low_turnover_low_amplitude_candidate():
    strategy = SteadyReversalSharpeStrategy(min_traded_value=0, max_atr_pct=1.0, holding_count=1)

    selected = strategy.screen(_sample_frame())

    assert selected["symbol"].tolist() == ["AAA"]
    assert selected["like_sharpe_10"].iloc[0] > 1
    assert selected["steady_reversal_score"].iloc[0] > 0


def test_steady_reversal_sharpe_generates_signals_only_on_rebalance_dates():
    strategy = SteadyReversalSharpeStrategy(min_traded_value=0, max_atr_pct=1.0, holding_count=1, rebalance_period=20)

    signals = strategy.generate_signals(_sample_frame())
    buy_dates = set(signals.loc[signals["buy_signal"], "date"].astype(str))

    assert "2024-01-21" in buy_dates
    assert "2024-01-22" not in buy_dates


def test_steady_reversal_sharpe_requires_turnover_by_default():
    frame = _sample_frame().drop(columns=["turnover"])
    strategy = SteadyReversalSharpeStrategy(min_traded_value=0, max_atr_pct=1.0, holding_count=1)

    selected = strategy.screen(frame)

    assert selected.empty


def test_steady_reversal_sharpe_can_load_from_yaml(tmp_path: Path):
    path = tmp_path / "steady.yaml"
    path.write_text(
        """
name: steady
strategy: steady_reversal_sharpe
params:
  min_like_sharpe: 1.2
  holding_count: 10
  rebalance_period: 20
""".strip(),
        encoding="utf-8",
    )

    strategy = create_strategy_from_config(path)

    assert isinstance(strategy, SteadyReversalSharpeStrategy)
    assert strategy.min_like_sharpe == 1.2
    assert strategy.holding_count == 10
