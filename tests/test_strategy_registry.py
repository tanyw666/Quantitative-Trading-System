from pathlib import Path

import pytest

from quant_system.strategies.dragon_leader import DragonLeaderStrategy
from quant_system.strategies.registry import create_strategy_from_config
from quant_system.strategies.strong_stock_screen import StrongStockScreen


def test_create_strategy_from_parameter_config(tmp_path: Path):
    path = tmp_path / "strategy.yaml"
    path.write_text(
        """
name: tuned_strong
strategy: strong_stock_screen
params:
  min_20d_return: 0.2
  min_volume_ratio: 2.0
  max_atr_pct: 0.08
""",
        encoding="utf-8",
    )

    strategy = create_strategy_from_config(path)

    assert isinstance(strategy, StrongStockScreen)
    assert strategy.min_20d_return == 0.2
    assert strategy.min_volume_ratio == 2.0
    assert strategy.max_atr_pct == 0.08
    assert strategy.scoring_weights == {}


def test_create_strategy_from_exported_dragon_config(tmp_path: Path):
    path = tmp_path / "dragon.yaml"
    path.write_text(
        """
name: tuned_dragon
strategy: dragon_leader
params:
  entry_gate: pass
  entry_model: next_open
  max_next_open_gap: 0.03
""",
        encoding="utf-8",
    )

    strategy = create_strategy_from_config(path)

    assert isinstance(strategy, DragonLeaderStrategy)
    assert strategy.entry_gate == "pass"
    assert strategy.entry_model == "next_open"
    assert strategy.max_next_open_gap == 0.03


def test_create_strategy_from_config_attaches_scoring_weights(tmp_path: Path):
    path = tmp_path / "weighted.yaml"
    path.write_text(
        """
name: weighted_strong
strategy: strong_stock_screen
params:
  min_20d_return: 0.2
scoring_weights:
  momentum_20: 0.8
  volume_ratio_20: 0.1
""",
        encoding="utf-8",
    )

    strategy = create_strategy_from_config(path)

    assert isinstance(strategy, StrongStockScreen)
    assert strategy.scoring_weights == {"momentum_20": 0.8, "volume_ratio_20": 0.1}


def test_create_strategy_from_config_attaches_constraint_policy(tmp_path: Path):
    path = tmp_path / "policy.yaml"
    path.write_text(
        """
name: policy_strong
strategy: strong_stock_screen
constraint_policy:
  window_days: 7
  single_block_pause: 2
  warn_exposure_multiplier: 0.4
""",
        encoding="utf-8",
    )

    strategy = create_strategy_from_config(path)

    assert isinstance(strategy, StrongStockScreen)
    assert strategy.constraint_policy["window_days"] == 7
    assert strategy.constraint_policy["single_block_pause"] == 2


def test_create_strategy_from_config_accepts_nested_risk_constraint_policy(tmp_path: Path):
    path = tmp_path / "nested_policy.yaml"
    path.write_text(
        """
name: nested_policy
strategy: strong_stock_screen
risk:
  constraint_policy:
    recover_after_clean_days: 5
""",
        encoding="utf-8",
    )

    strategy = create_strategy_from_config(path)

    assert strategy.constraint_policy["recover_after_clean_days"] == 5


def test_create_strategy_from_legacy_name_config(tmp_path: Path):
    path = tmp_path / "legacy.yaml"
    path.write_text(
        """
name: strong_stock_screen
params:
  min_20d_return: 0.2
""",
        encoding="utf-8",
    )

    strategy = create_strategy_from_config(path)

    assert isinstance(strategy, StrongStockScreen)
    assert strategy.min_20d_return == 0.2


def test_create_strategy_from_config_rejects_non_mapping_root(tmp_path: Path):
    path = tmp_path / "broken.yaml"
    path.write_text("- not-a-mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a mapping"):
        create_strategy_from_config(path)
