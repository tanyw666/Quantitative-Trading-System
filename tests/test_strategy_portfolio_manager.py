from pathlib import Path

import pandas as pd

from quant_system.risk.sizing import build_allocation_plan
from quant_system.strategies.portfolio_manager import (
    StrategyPortfolioConfig,
    build_strategy_portfolio_plan,
)


def _sample_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=70)
    aaa_close = [10 + index * 0.18 for index in range(70)]
    bbb_close = [10 + index * 0.035 for index in range(70)]
    return pd.DataFrame(
        {
            "date": list(dates) * 2,
            "symbol": ["AAA"] * 70 + ["BBB"] * 70,
            "open": [value - 0.05 for value in aaa_close] + [value - 0.02 for value in bbb_close],
            "high": [value + 0.25 for value in aaa_close] + [value + 0.08 for value in bbb_close],
            "low": [value - 0.25 for value in aaa_close] + [value - 0.08 for value in bbb_close],
            "close": aaa_close + bbb_close,
            "volume": ([1000] * 69 + [2600]) + ([900] * 69 + [950]),
            "turnover": [3.0] * 70 + [1.0] * 70,
        }
    )


def _portfolio_config() -> StrategyPortfolioConfig:
    return StrategyPortfolioConfig.from_mapping(
        {
            "name": "test_portfolio",
            "duplicate_vote_bonus": 6.0,
            "sleeves": [
                {
                    "name": "attack",
                    "strategy": "strong_stock_screen",
                    "role": "main_attack",
                    "enabled_regimes": ["warm"],
                    "budget_pct_by_regime": {"warm": 0.42},
                    "max_candidates": 2,
                    "params": {
                        "min_20d_return": 0.05,
                        "min_volume_ratio": 1.0,
                        "max_volume_ratio": 5.0,
                        "max_atr_pct": 0.5,
                        "max_close_ma20_gap": 1.0,
                        "min_entry_structure_score": 0.0,
                        "max_chase_risk_score": 100.0,
                    },
                },
                {
                    "name": "defensive",
                    "strategy": "steady_reversal_sharpe",
                    "role": "defensive_supplement",
                    "enabled_regimes": ["warm", "cold"],
                    "budget_pct_by_regime": {"warm": 0.18, "cold": 0.08},
                    "max_candidates": 2,
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


def test_strategy_portfolio_runs_active_sleeves_and_marks_budget_caps():
    plan = build_strategy_portfolio_plan(
        _sample_frame(),
        _portfolio_config(),
        market_temperature={"score": 60, "regime": "warm", "stance": "test"},
    )

    assert [item.status for item in plan.sleeves] == ["active", "active"]
    assert not plan.candidates.empty
    assert {"source_strategy", "strategy_budget_pct", "position_cap_pct", "portfolio_score"}.issubset(plan.candidates.columns)
    assert plan.candidates["position_cap_pct"].max() <= 0.20


def test_strategy_portfolio_skips_sleeves_that_are_disabled_by_regime():
    plan = build_strategy_portfolio_plan(
        _sample_frame(),
        _portfolio_config(),
        market_temperature={"score": 20, "regime": "cold", "stance": "test"},
    )

    statuses = {item.name: item.status for item in plan.sleeves}
    assert statuses["attack"] == "skipped"
    assert statuses["defensive"] == "active"
    assert set(plan.candidates["source_strategy"]) == {"defensive"}


def test_strategy_portfolio_merges_duplicate_strategy_votes():
    config = StrategyPortfolioConfig.from_mapping(
        {
            "name": "duplicate_test",
            "duplicate_vote_bonus": 7.0,
            "sleeves": [
                {
                    "name": "attack_a",
                    "strategy": "strong_stock_screen",
                    "enabled_regimes": ["warm"],
                    "budget_pct_by_regime": {"warm": 0.20},
                    "params": {
                        "min_20d_return": 0.05,
                        "min_volume_ratio": 1.0,
                        "max_volume_ratio": 5.0,
                        "max_atr_pct": 0.5,
                        "max_close_ma20_gap": 1.0,
                        "min_entry_structure_score": 0.0,
                        "max_chase_risk_score": 100.0,
                    },
                },
                {
                    "name": "attack_b",
                    "strategy": "strong_stock_screen",
                    "enabled_regimes": ["warm"],
                    "budget_pct_by_regime": {"warm": 0.20},
                    "params": {
                        "min_20d_return": 0.05,
                        "min_volume_ratio": 1.0,
                        "max_volume_ratio": 5.0,
                        "max_atr_pct": 0.5,
                        "max_close_ma20_gap": 1.0,
                        "min_entry_structure_score": 0.0,
                        "max_chase_risk_score": 100.0,
                    },
                },
            ],
        }
    )

    plan = build_strategy_portfolio_plan(
        _sample_frame(),
        config,
        market_temperature={"score": 60, "regime": "warm", "stance": "test"},
    )

    row = plan.candidates.iloc[0]
    assert row["strategy_vote_count"] == 2
    assert row["strategy_votes"] == "attack_a,attack_b"
    assert row["position_cap_pct"] == 0.2


def test_allocation_plan_respects_portfolio_position_cap():
    candidates = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "name": "A",
                "score": 100,
                "risk_grade": "low",
                "position_cap_pct": 0.05,
                "close": 10,
            }
        ]
    )

    plan = build_allocation_plan(
        candidates,
        {"regime": "hot", "stance": "test"},
        cash=100000,
        max_positions=1,
    )

    assert plan.items[0].target_pct == 0.05
    assert plan.items[0].target_value == 5000


def test_strategy_portfolio_config_loads_relative_strategy_paths(tmp_path: Path):
    strategy_path = tmp_path / "strong.yaml"
    strategy_path.write_text(
        """
name: strong_for_portfolio
strategy: strong_stock_screen
params:
  min_20d_return: 0.05
  min_volume_ratio: 1.0
  max_atr_pct: 0.5
""".strip()
        + "\n",
        encoding="utf-8",
    )
    portfolio_path = tmp_path / "portfolio.yaml"
    portfolio_path.write_text(
        """
name: path_portfolio
sleeves:
  - name: strong_for_portfolio
    config: strong.yaml
    enabled_regimes: [warm]
    budget_pct_by_regime:
      warm: 0.2
""".strip()
        + "\n",
        encoding="utf-8",
    )

    config = StrategyPortfolioConfig.from_yaml(portfolio_path)

    assert config.sleeves[0].config_path == strategy_path
