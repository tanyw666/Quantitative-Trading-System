from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_SCORING_WEIGHTS = {
    "momentum_20": 0.35,
    "volume_ratio_20": 0.18,
    "atr_pct_14": 0.12,
    "sector_strength_score": 0.10,
    "ma20_slope_5": 0.12,
    "close_to_ma20": 0.05,
    "traded_value": 0.05,
    "rsi_14": 0.03,
    "trend_quality_score": 0.05,
    "entry_structure_score": 0.08,
    "chase_risk_score": 0.05,
    "candle_warning_count": 0.02,
    "tape_pressure_score": 0.04,
    "tape_distribution_warning": 0.03,
    "volume_confirmation_score": 0.03,
    "candle_quality_score": 0.03,
    "breakout_quality_score": 0.04,
    "false_breakout_pressure": 0.03,
}

DEFAULT_REGIME_EXPOSURE = {
    "hot": 0.80,
    "warm": 0.60,
    "neutral": 0.30,
    "cold": 0.10,
    "frozen": 0.0,
    "empty": 0.0,
}

DEFAULT_RISK_CAP = {
    "low": 0.20,
    "medium": 0.12,
    "high": 0.06,
    "unknown": 0.05,
}

DEFAULT_CONSTRAINT_POLICY = {
    "window_days": 5.0,
    "cooldown_block_count": 2.0,
    "single_block_pause": 1.0,
    "warn_escalation_count": 2.0,
    "recover_after_clean_days": 3.0,
    "recover_probe_days": 2.0,
    "recover_probe_exposure_multiplier": 0.25,
    "recover_trade_plan_match_rate_min": 0.9,
    "recover_max_unmatched_plans": 0.0,
    "recover_max_orphan_trades": 0.0,
    "warn_exposure_multiplier": 0.5,
}


@dataclass(frozen=True)
class ScoringSettings:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SCORING_WEIGHTS))


@dataclass(frozen=True)
class ConstraintPolicySettings:
    window_days: int = 5
    cooldown_block_count: int = 2
    single_block_pause: int = 1
    warn_escalation_count: int = 2
    recover_after_clean_days: int = 3
    recover_probe_days: int = 2
    recover_probe_exposure_multiplier: float = 0.25
    recover_trade_plan_match_rate_min: float = 0.9
    recover_max_unmatched_plans: int = 0
    recover_max_orphan_trades: int = 0
    warn_exposure_multiplier: float = 0.5
    strategy_overrides: dict[str, dict[str, float]] = field(default_factory=dict)

    def kwargs_for(self, strategy: str = "") -> dict[str, float | int]:
        values: dict[str, float | int] = {
            "window_days": self.window_days,
            "cooldown_block_count": self.cooldown_block_count,
            "single_block_pause": self.single_block_pause,
            "warn_escalation_count": self.warn_escalation_count,
            "recover_after_clean_days": self.recover_after_clean_days,
            "recover_probe_days": self.recover_probe_days,
            "recover_probe_exposure_multiplier": self.recover_probe_exposure_multiplier,
            "recover_trade_plan_match_rate_min": self.recover_trade_plan_match_rate_min,
            "recover_max_unmatched_plans": self.recover_max_unmatched_plans,
            "recover_max_orphan_trades": self.recover_max_orphan_trades,
            "warn_exposure_multiplier": self.warn_exposure_multiplier,
        }
        override = self.strategy_overrides.get(_normalize_strategy_name(strategy), {})
        for key, value in override.items():
            if key in {
                "window_days",
                "cooldown_block_count",
                "single_block_pause",
                "warn_escalation_count",
                "recover_after_clean_days",
                "recover_probe_days",
                "recover_max_unmatched_plans",
                "recover_max_orphan_trades",
            }:
                values[key] = int(value)
            elif key in {
                "warn_exposure_multiplier",
                "recover_probe_exposure_multiplier",
                "recover_trade_plan_match_rate_min",
            }:
                values[key] = float(value)
        return values

    def to_mapping(self) -> dict[str, Any]:
        return {
            "window_days": self.window_days,
            "cooldown_block_count": self.cooldown_block_count,
            "single_block_pause": self.single_block_pause,
            "warn_escalation_count": self.warn_escalation_count,
            "recover_after_clean_days": self.recover_after_clean_days,
            "recover_probe_days": self.recover_probe_days,
            "recover_probe_exposure_multiplier": self.recover_probe_exposure_multiplier,
            "recover_trade_plan_match_rate_min": self.recover_trade_plan_match_rate_min,
            "recover_max_unmatched_plans": self.recover_max_unmatched_plans,
            "recover_max_orphan_trades": self.recover_max_orphan_trades,
            "warn_exposure_multiplier": self.warn_exposure_multiplier,
            "strategies": self.strategy_overrides,
        }


@dataclass(frozen=True)
class RiskSettings:
    regime_exposure: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_REGIME_EXPOSURE))
    cap_by_risk: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RISK_CAP))
    constraint_policy: ConstraintPolicySettings = field(default_factory=ConstraintPolicySettings)


@dataclass(frozen=True)
class DataSourceSettings:
    daily_source: str = "auto"
    universe_source: str = "auto"
    concept_source: str = "auto"
    announcement_source: str = "auto"
    news_source: str = "auto"
    global_source: str = "auto"
    wencai_source: str = "auto"


@dataclass(frozen=True)
class TradingDaySettings:
    phases: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class SystemSettings:
    scoring: ScoringSettings = field(default_factory=ScoringSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)
    data_sources: DataSourceSettings = field(default_factory=DataSourceSettings)
    trading_day: TradingDaySettings = field(default_factory=TradingDaySettings)

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any] | None) -> "SystemSettings":
        mapping = mapping or {}
        scoring_mapping = _require_mapping(mapping.get("scoring", {}), "scoring")
        risk_mapping = _require_mapping(mapping.get("risk", {}), "risk")
        legacy_data_mapping = _require_mapping(mapping.get("data", {}), "data")
        data_mapping = _require_mapping(mapping.get("data_sources", {}), "data_sources")
        trading_day_mapping = _require_mapping(mapping.get("trading_day", {}), "trading_day")
        return cls(
            scoring=ScoringSettings(weights=_merge(DEFAULT_SCORING_WEIGHTS, _require_mapping(scoring_mapping.get("weights", {}), "scoring.weights"))),
            risk=RiskSettings(
                regime_exposure=_merge(
                    DEFAULT_REGIME_EXPOSURE,
                    _require_mapping(risk_mapping.get("regime_exposure", {}), "risk.regime_exposure"),
                ),
                cap_by_risk=_merge(
                    DEFAULT_RISK_CAP,
                    _require_mapping(risk_mapping.get("cap_by_risk", {}), "risk.cap_by_risk"),
                ),
                constraint_policy=_constraint_policy_settings(
                    _require_mapping(risk_mapping.get("constraint_policy", {}), "risk.constraint_policy")
                ),
            ),
            data_sources=DataSourceSettings(
                daily_source=str(data_mapping.get("daily_source", legacy_data_mapping.get("primary_source", "auto"))),
                universe_source=str(data_mapping.get("universe_source", "auto")),
                concept_source=str(data_mapping.get("concept_source", "auto")),
                announcement_source=str(data_mapping.get("announcement_source", "auto")),
                news_source=str(data_mapping.get("news_source", "auto")),
                global_source=str(data_mapping.get("global_source", "auto")),
                wencai_source=str(data_mapping.get("wencai_source", "auto")),
            ),
            trading_day=TradingDaySettings(
                phases=_phase_template_mapping(
                    _require_mapping(trading_day_mapping.get("phases", {}), "trading_day.phases")
                ),
            ),
        )


def load_settings(path: Path | None) -> SystemSettings:
    if path is None:
        return SystemSettings()

    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load settings. Run: python -m pip install -e .[dev]") from exc

    with path.open("r", encoding="utf-8") as handle:
        mapping = yaml.safe_load(handle) or {}
    if not isinstance(mapping, dict):
        raise ValueError("Settings file must contain a mapping at the root")
    return SystemSettings.from_mapping(mapping)


def _merge(defaults: dict[str, float], override: dict[str, Any] | None) -> dict[str, float]:
    merged = dict(defaults)
    if override:
        for key, value in override.items():
            if value is None:
                continue
            merged[str(key)] = float(value)
    return merged


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _phase_template_mapping(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    phases: dict[str, dict[str, Any]] = {}
    for phase, raw in value.items():
        mapping = _require_mapping(raw, f"trading_day.phases.{phase}")
        phases[str(phase)] = dict(mapping)
    return phases


def _constraint_policy_settings(mapping: dict[str, Any]) -> ConstraintPolicySettings:
    raw_overrides = _require_mapping(mapping.get("strategies", {}), "risk.constraint_policy.strategies")
    numeric_override = {key: value for key, value in mapping.items() if key != "strategies"}
    merged = _merge(DEFAULT_CONSTRAINT_POLICY, numeric_override)
    strategy_overrides = {
        _normalize_strategy_name(strategy): _merge(
            {},
            _require_mapping(value, f"risk.constraint_policy.strategies.{strategy}"),
        )
        for strategy, value in raw_overrides.items()
    }
    return ConstraintPolicySettings(
        window_days=int(merged.get("window_days", 5)),
        cooldown_block_count=int(merged.get("cooldown_block_count", 2)),
        single_block_pause=int(merged.get("single_block_pause", 1)),
        warn_escalation_count=int(merged.get("warn_escalation_count", 2)),
        recover_after_clean_days=int(merged.get("recover_after_clean_days", 3)),
        recover_probe_days=int(merged.get("recover_probe_days", 2)),
        recover_probe_exposure_multiplier=float(merged.get("recover_probe_exposure_multiplier", 0.25)),
        recover_trade_plan_match_rate_min=float(merged.get("recover_trade_plan_match_rate_min", 0.9)),
        recover_max_unmatched_plans=int(merged.get("recover_max_unmatched_plans", 0)),
        recover_max_orphan_trades=int(merged.get("recover_max_orphan_trades", 0)),
        warn_exposure_multiplier=float(merged.get("warn_exposure_multiplier", 0.5)),
        strategy_overrides=strategy_overrides,
    )


def _normalize_strategy_name(strategy: str) -> str:
    return str(strategy).strip().lower().replace("-", "_")
