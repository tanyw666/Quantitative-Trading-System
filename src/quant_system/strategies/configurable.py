from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_system.factors.technical import add_core_factors
from quant_system.screening.scoring import score_candidates
from quant_system.strategies.conditions import evaluate_condition


class ConfigurableScreenStrategy:
    def __init__(self, name: str, condition: dict[str, Any], description: str = "") -> None:
        self.name = name
        self.condition = condition
        self.description = description

    @classmethod
    def from_mapping(cls, config: dict[str, Any]) -> "ConfigurableScreenStrategy":
        return cls(
            name=str(config["name"]),
            description=str(config.get("description", "")),
            condition=dict(config["condition"]),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "ConfigurableScreenStrategy":
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PyYAML is not installed. Run: python -m pip install -e .[dev]") from exc

        with path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        return cls.from_mapping(config)

    def generate_signals(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = add_core_factors(frame)
        results = data.apply(lambda row: evaluate_condition(row, self.condition), axis=1)
        data["buy_signal"] = [result.passed for result in results]
        data["sell_signal"] = False
        data["reason"] = [result.reason for result in results]
        return data

    def screen(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = self.generate_signals(frame)
        latest = data.groupby("symbol").tail(1) if "symbol" in data.columns else data.tail(1)
        selected = score_candidates(latest[latest["buy_signal"]].copy())
        columns = [
            col
            for col in (
                "date",
                "symbol",
                "name",
                "market",
                "board",
                "industry",
                "sector",
                "close",
                "score",
                "risk_grade",
                "atr_stop_price",
                "momentum_20",
                "volume_ratio_20",
                "atr_14",
                "atr_pct_14",
                "reason",
            )
            if col in selected.columns
        ]
        return selected[columns].reset_index(drop=True)
