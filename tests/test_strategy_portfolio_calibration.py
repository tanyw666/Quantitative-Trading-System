import pandas as pd

from quant_system.optimizer.strategy_portfolio_calibration import (
    PortfolioCalibrationVariant,
    StrategyPortfolioBacktestStrategy,
    default_portfolio_calibration_variants,
    render_strategy_portfolio_calibration_markdown,
    run_strategy_portfolio_calibration,
)
from quant_system.strategies.portfolio_manager import StrategyPortfolioConfig


def _sample_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=80)
    aaa_close = [10 + index * 0.15 for index in range(80)]
    bbb_close = [10 + index * 0.04 for index in range(80)]
    return pd.DataFrame(
        {
            "date": list(dates) * 2,
            "symbol": ["000001"] * 80 + ["000002"] * 80,
            "open": [value - 0.05 for value in aaa_close] + [value - 0.02 for value in bbb_close],
            "high": [value + 0.25 for value in aaa_close] + [value + 0.08 for value in bbb_close],
            "low": [value - 0.25 for value in aaa_close] + [value - 0.08 for value in bbb_close],
            "close": aaa_close + bbb_close,
            "volume": ([1000] * 79 + [2600]) + ([900] * 79 + [950]),
            "turnover": [2.0] * 80 + [1.0] * 80,
        }
    )


def _portfolio_config() -> StrategyPortfolioConfig:
    return StrategyPortfolioConfig.from_mapping(
        {
            "name": "calibration_portfolio",
            "duplicate_vote_bonus": 6.0,
            "max_position_pct": 0.2,
            "sleeves": [
                {
                    "name": "attack",
                    "strategy": "strong_stock_screen",
                    "role": "main_attack",
                    "enabled_regimes": ["hot", "warm", "neutral", "cold"],
                    "budget_pct_by_regime": {"hot": 0.4, "warm": 0.4, "neutral": 0.2, "cold": 0.1},
                    "params": {
                        "min_20d_return": 0.03,
                        "min_volume_ratio": 0.5,
                        "max_volume_ratio": 10.0,
                        "max_atr_pct": 1.0,
                        "max_close_ma20_gap": 2.0,
                        "min_entry_structure_score": 0.0,
                        "max_chase_risk_score": 100.0,
                        "max_candle_warning_count": 5,
                        "block_false_breakout": False,
                    },
                },
                {
                    "name": "defensive",
                    "strategy": "steady_reversal_sharpe",
                    "role": "defensive_supplement",
                    "enabled_regimes": ["hot", "warm", "neutral", "cold"],
                    "budget_pct_by_regime": {"hot": 0.15, "warm": 0.18, "neutral": 0.16, "cold": 0.08},
                    "params": {
                        "min_like_sharpe": 0.1,
                        "holding_count": 2,
                        "rebalance_period": 20,
                        "max_atr_pct": 0.5,
                        "require_turnover": True,
                    },
                },
            ],
        }
    )


def test_portfolio_backtest_strategy_generates_rebalance_signals():
    strategy = StrategyPortfolioBacktestStrategy(
        _portfolio_config(),
        max_positions=2,
        rebalance_period=5,
        min_history_days=25,
    )

    signals = strategy.generate_signals(_sample_frame())

    assert "buy_signal" in signals.columns
    assert int(signals["buy_signal"].sum()) > 0


def test_run_strategy_portfolio_calibration_ranks_variants():
    summary = run_strategy_portfolio_calibration(
        _sample_frame(),
        _portfolio_config(),
        variants=[
            PortfolioCalibrationVariant(
                name="baseline",
                role_budget_multipliers={"main_attack": 1.0, "defensive_supplement": 1.0},
                duplicate_vote_bonus=6.0,
                max_position_pct=0.2,
            ),
            PortfolioCalibrationVariant(
                name="defensive",
                role_budget_multipliers={"main_attack": 0.75, "defensive_supplement": 1.25},
                duplicate_vote_bonus=4.0,
                max_position_pct=0.14,
            ),
        ],
        rebalance_period=5,
        max_positions=2,
        min_history_days=25,
    )

    assert summary["case_count"] == 2
    assert summary["best"]["variant"]["name"] in {"baseline", "defensive"}
    assert len(summary["cases"]) == 2
    assert "max_position_pct" in summary["sensitivity"]


def test_render_strategy_portfolio_calibration_markdown_contains_ranking():
    summary = run_strategy_portfolio_calibration(
        _sample_frame(),
        _portfolio_config(),
        variants=default_portfolio_calibration_variants("compact")[:2],
        rebalance_period=5,
        max_positions=2,
        min_history_days=25,
    )

    markdown = render_strategy_portfolio_calibration_markdown(summary)

    assert "# Strategy Portfolio Calibration" in markdown
    assert "## Ranking" in markdown
    assert "baseline" in markdown
