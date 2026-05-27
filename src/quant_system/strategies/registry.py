from __future__ import annotations

from quant_system.strategies.strong_stock_screen import StrongStockScreen
from quant_system.strategies.trend_breakout import TrendBreakoutStrategy
from quant_system.strategies.configurable import ConfigurableScreenStrategy
from quant_system.strategies.dragon_leader import DragonLeaderStrategy


def create_strategy(name: str, **kwargs):
    normalized = name.strip().lower().replace("-", "_")
    if normalized == "trend_breakout":
        return TrendBreakoutStrategy()
    if normalized == "strong_stock_screen":
        return StrongStockScreen()
    if normalized == "dragon_leader":
        return DragonLeaderStrategy(**kwargs)
    raise ValueError(f"Unknown strategy: {name}")


def create_strategy_from_config(path):
    return ConfigurableScreenStrategy.from_yaml(path)
