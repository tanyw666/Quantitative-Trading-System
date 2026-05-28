from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from quant_system.screening.scoring import SUPPORTED_SCORE_COLUMNS
from quant_system.strategies.registry import create_strategy_from_config


@dataclass(frozen=True)
class StrategyConfigValidation:
    path: str
    ok: bool
    strategy_type: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    smoke: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "ok": self.ok,
            "strategy_type": self.strategy_type,
            "warnings": self.warnings,
            "errors": self.errors,
            "smoke": self.smoke,
        }


def validate_strategy_config(path: Path, frame: pd.DataFrame | None = None) -> StrategyConfigValidation:
    warnings: list[str] = []
    errors: list[str] = []
    strategy_type = ""
    smoke: dict[str, Any] = {}

    try:
        strategy = create_strategy_from_config(path)
        strategy_type = type(strategy).__name__
    except Exception as exc:  # noqa: BLE001 - validation should report config errors structurally.
        return StrategyConfigValidation(path=str(path), ok=False, strategy_type="", errors=[str(exc)])

    weights = getattr(strategy, "scoring_weights", {}) or {}
    unsupported_weights = sorted(set(weights) - set(SUPPORTED_SCORE_COLUMNS))
    if unsupported_weights:
        warnings.append(f"Unsupported scoring weights ignored by scorer: {', '.join(unsupported_weights)}")

    if frame is not None:
        try:
            selected = strategy.screen(frame)
            smoke = {
                "rows": int(len(selected)),
                "columns": list(selected.columns),
            }
        except Exception as exc:  # noqa: BLE001 - smoke failures should be reported without crashing caller.
            errors.append(f"Smoke screen failed: {exc}")

    return StrategyConfigValidation(
        path=str(path),
        ok=not errors,
        strategy_type=strategy_type,
        warnings=warnings,
        errors=errors,
        smoke=smoke,
    )


def validate_strategy_directory(path: Path, frame: pd.DataFrame | None = None) -> list[StrategyConfigValidation]:
    files = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml"))
    return [validate_strategy_config(item, frame=frame) for item in files]
