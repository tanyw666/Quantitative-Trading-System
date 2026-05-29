from __future__ import annotations

from pathlib import Path
from typing import Any

from quant_system.strategies.strong_stock_screen import StrongStockScreen
from quant_system.strategies.trend_breakout import TrendBreakoutStrategy
from quant_system.strategies.configurable import ConfigurableScreenStrategy
from quant_system.strategies.dragon_leader import DragonLeaderStrategy


def create_strategy(name: str, **kwargs):
    normalized = name.strip().lower().replace("-", "_")
    if normalized == "trend_breakout":
        return TrendBreakoutStrategy(**kwargs)
    if normalized == "strong_stock_screen":
        return StrongStockScreen(**kwargs)
    if normalized == "dragon_leader":
        return DragonLeaderStrategy(**kwargs)
    raise ValueError(f"Unknown strategy: {name}")


def create_strategy_from_config(path):
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyYAML is not installed. Run: python -m pip install -e .[dev]") from exc

    config = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise ValueError(f"Strategy config must contain a mapping at the root: {path}")
    if "condition" in config:
        return ConfigurableScreenStrategy.from_mapping(config)
    strategy_name = str(config.get("strategy", "")).strip()
    if not strategy_name and str(config.get("name", "")).strip():
        strategy_name = str(config.get("name", "")).strip()
    if not strategy_name:
        raise ValueError(f"Strategy config missing 'condition' or 'strategy': {path}")
    strategy = create_strategy(strategy_name, **dict(config.get("params", {}) or {}))
    _attach_config_metadata(strategy, config)
    return strategy


def _attach_config_metadata(strategy: Any, config: dict[str, Any]) -> None:
    strategy.config_name = config.get("name", "")
    strategy.config_description = config.get("description", "")
    strategy.scoring_weights = dict(config.get("scoring_weights", {}) or {})
    risk = config.get("risk", {}) if isinstance(config.get("risk", {}), dict) else {}
    strategy.constraint_policy = dict(
        config.get("constraint_policy", {})
        or (risk.get("constraint_policy", {}) if isinstance(risk, dict) else {})
        or {}
    )
