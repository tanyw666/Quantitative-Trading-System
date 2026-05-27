from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_SCORING_WEIGHTS = {
    "momentum_20": 0.50,
    "volume_ratio_20": 0.30,
    "atr_pct_14": 0.20,
    "sector_strength_score": 0.15,
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


@dataclass(frozen=True)
class ScoringSettings:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SCORING_WEIGHTS))


@dataclass(frozen=True)
class RiskSettings:
    regime_exposure: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_REGIME_EXPOSURE))
    cap_by_risk: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RISK_CAP))


@dataclass(frozen=True)
class SystemSettings:
    scoring: ScoringSettings = field(default_factory=ScoringSettings)
    risk: RiskSettings = field(default_factory=RiskSettings)

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any] | None) -> "SystemSettings":
        mapping = mapping or {}
        scoring_mapping = mapping.get("scoring", {})
        risk_mapping = mapping.get("risk", {})
        return cls(
            scoring=ScoringSettings(weights=_merge(DEFAULT_SCORING_WEIGHTS, scoring_mapping.get("weights"))),
            risk=RiskSettings(
                regime_exposure=_merge(DEFAULT_REGIME_EXPOSURE, risk_mapping.get("regime_exposure")),
                cap_by_risk=_merge(DEFAULT_RISK_CAP, risk_mapping.get("cap_by_risk")),
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
