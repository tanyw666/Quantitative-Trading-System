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
    score: float = 0.0
    status: str = ""
    action: str = ""
    alerts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    smoke: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "ok": self.ok,
            "strategy_type": self.strategy_type,
            "score": self.score,
            "status": self.status,
            "action": self.action,
            "alerts": self.alerts,
            "warnings": self.warnings,
            "errors": self.errors,
            "smoke": self.smoke,
        }


def validate_strategy_config(
    path: Path,
    frame: pd.DataFrame | None = None,
    trade_plan_pressure: dict[str, Any] | None = None,
) -> StrategyConfigValidation:
    warnings: list[str] = []
    errors: list[str] = []
    strategy_type = ""
    smoke: dict[str, Any] = {}
    score = 100.0
    status = "ok"
    action = "keep"
    alerts: list[str] = []

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

    if trade_plan_pressure:
        score, status, action, alerts, warnings = _apply_trade_plan_pressure(
            score,
            status,
            action,
            alerts,
            warnings,
            trade_plan_pressure,
        )
    if errors:
        score = min(score, 0.0)
        status = "fail"
        action = "pause"

    return StrategyConfigValidation(
        path=str(path),
        ok=not errors,
        strategy_type=strategy_type,
        score=round(max(score, 0.0), 2),
        status=status,
        action=action,
        alerts=_unique(alerts),
        warnings=warnings,
        errors=errors,
        smoke=smoke,
    )


def validate_strategy_directory(
    path: Path,
    frame: pd.DataFrame | None = None,
    trade_plan_pressure: dict[str, Any] | None = None,
) -> list[StrategyConfigValidation]:
    files = sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml"))
    return [validate_strategy_config(item, frame=frame, trade_plan_pressure=trade_plan_pressure) for item in files]


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for item in values:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result


def _apply_trade_plan_pressure(
    score: float,
    status: str,
    action: str,
    alerts: list[str],
    warnings: list[str],
    pressure: dict[str, Any],
) -> tuple[float, str, str, list[str], list[str]]:
    adjusted_score = float(score)
    adjusted_status = str(status or "")
    adjusted_action = str(action or "")
    adjusted_alerts = list(alerts)
    adjusted_warnings = list(warnings)

    match_rate = float(pressure.get("match_rate", 0) or 0)
    unmatched_plans = int(pressure.get("unmatched_plans", 0) or 0)
    orphan_trades = int(pressure.get("orphan_trades", 0) or 0)
    avg_price_deviation_pct = abs(float(pressure.get("avg_price_deviation_pct", 0) or 0))

    if match_rate < 0.7 or orphan_trades >= 2 or unmatched_plans >= 3:
        adjusted_score -= 18
        adjusted_status = "warn"
        adjusted_action = "reduce"
        adjusted_alerts = _unique([*adjusted_alerts, "trade_plan_mismatch", "trade_plan_block"])
        adjusted_warnings.append("Trade plan audit shows persistent mismatch between planned and actual trades.")
    elif match_rate < 0.85 or unmatched_plans > 0 or orphan_trades > 0 or avg_price_deviation_pct > 0.03:
        adjusted_score -= 8
        if adjusted_status not in {"warn", "fail"}:
            adjusted_status = "watch"
        if adjusted_action == "keep":
            adjusted_action = "reduce"
        adjusted_alerts = _unique([*adjusted_alerts, "trade_plan_drift"])
        adjusted_warnings.append("Trade plan audit shows drift; verify execution discipline before promotion.")

    return round(max(adjusted_score, 0.0), 2), adjusted_status, adjusted_action, _unique(adjusted_alerts), adjusted_warnings
