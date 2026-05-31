from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from quant_system.market.temperature import MarketTemperature, calculate_market_temperature
from quant_system.strategies.registry import create_strategy, create_strategy_from_config


DEFAULT_REGIME_BUDGET = {
    "hot": 0.0,
    "warm": 0.0,
    "neutral": 0.0,
    "cold": 0.0,
    "frozen": 0.0,
    "empty": 0.0,
}


@dataclass(frozen=True)
class StrategySleeveConfig:
    name: str
    role: str = "satellite"
    enabled: bool = True
    config_path: Path | None = None
    strategy: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    enabled_regimes: tuple[str, ...] = ("hot", "warm", "neutral", "cold")
    budget_pct_by_regime: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_REGIME_BUDGET))
    max_candidates: int = 5
    min_score: float | None = None
    score_weight: float = 1.0
    vote_bonus: float = 5.0

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any], *, base_dir: Path | None = None) -> "StrategySleeveConfig":
        raw_path = mapping.get("config") or mapping.get("config_path")
        config_path = None
        if raw_path:
            config_path = Path(str(raw_path))
            if base_dir is not None and not config_path.is_absolute():
                config_path = base_dir / config_path
        budgets = dict(DEFAULT_REGIME_BUDGET)
        for key, value in dict(mapping.get("budget_pct_by_regime", {}) or {}).items():
            budgets[str(key)] = float(value)
        return cls(
            name=str(mapping.get("name") or mapping.get("strategy") or "").strip(),
            role=str(mapping.get("role", "satellite") or "satellite"),
            enabled=bool(mapping.get("enabled", True)),
            config_path=config_path,
            strategy=str(mapping.get("strategy", "") or "").strip() or None,
            params=dict(mapping.get("params", {}) or {}),
            enabled_regimes=tuple(str(item) for item in mapping.get("enabled_regimes", ("hot", "warm", "neutral", "cold"))),
            budget_pct_by_regime=budgets,
            max_candidates=max(int(mapping.get("max_candidates", 5) or 5), 0),
            min_score=float(mapping["min_score"]) if mapping.get("min_score") not in (None, "") else None,
            score_weight=float(mapping.get("score_weight", 1.0) or 1.0),
            vote_bonus=float(mapping.get("vote_bonus", 5.0) or 0.0),
        )

    def load_strategy(self):
        if self.config_path is not None:
            return create_strategy_from_config(self.config_path)
        if not self.strategy:
            raise ValueError(f"Strategy sleeve {self.name!r} missing config or strategy")
        return create_strategy(self.strategy, **self.params)


@dataclass(frozen=True)
class StrategyPortfolioConfig:
    name: str = "adaptive_strategy_portfolio"
    description: str = ""
    sleeves: tuple[StrategySleeveConfig, ...] = ()
    duplicate_vote_bonus: float = 5.0
    max_position_pct: float = 0.20

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any], *, base_dir: Path | None = None) -> "StrategyPortfolioConfig":
        raw_sleeves = mapping.get("sleeves", []) or []
        if not isinstance(raw_sleeves, list):
            raise ValueError("strategy portfolio 'sleeves' must be a list")
        sleeves = tuple(
            StrategySleeveConfig.from_mapping(item, base_dir=base_dir)
            for item in raw_sleeves
            if isinstance(item, dict)
        )
        if not sleeves:
            raise ValueError("strategy portfolio must contain at least one sleeve")
        return cls(
            name=str(mapping.get("name", "adaptive_strategy_portfolio") or "adaptive_strategy_portfolio"),
            description=str(mapping.get("description", "") or ""),
            sleeves=sleeves,
            duplicate_vote_bonus=float(mapping.get("duplicate_vote_bonus", 5.0) or 0.0),
            max_position_pct=max(float(mapping.get("max_position_pct", 0.20) or 0.20), 0.0),
        )

    @classmethod
    def from_yaml(cls, path: Path) -> "StrategyPortfolioConfig":
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to load strategy portfolio config") from exc

        mapping = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(mapping, dict):
            raise ValueError(f"Strategy portfolio config must contain a mapping: {path}")
        return cls.from_mapping(mapping, base_dir=path.parent)


@dataclass(frozen=True)
class StrategySleeveDecision:
    name: str
    role: str
    status: str
    regime: str
    budget_pct: float
    candidate_count: int
    selected_count: int
    reason: str
    health_alert_level: str = "pass"
    health_action: str = "keep"
    exposure_multiplier: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyPortfolioPlan:
    name: str
    market_temperature: MarketTemperature
    sleeves: tuple[StrategySleeveDecision, ...]
    candidates: pd.DataFrame

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "market_temperature": self.market_temperature.to_dict(),
            "sleeves": [item.to_dict() for item in self.sleeves],
            "candidate_count": len(self.candidates),
            "candidates": self.candidates.to_dict(orient="records"),
        }


def build_strategy_portfolio_plan(
    frame: pd.DataFrame,
    config: StrategyPortfolioConfig,
    *,
    market_temperature: MarketTemperature | dict[str, Any] | None = None,
    strategy_health_by_name: dict[str, dict[str, Any]] | None = None,
) -> StrategyPortfolioPlan:
    temperature = _normalize_temperature(frame, market_temperature)
    regime = temperature.regime
    health_by_name = {_normalize_name(key): value for key, value in dict(strategy_health_by_name or {}).items()}
    decisions: list[StrategySleeveDecision] = []
    candidate_frames: list[pd.DataFrame] = []

    for sleeve in config.sleeves:
        health = health_by_name.get(_normalize_name(sleeve.name), {})
        multiplier = _health_exposure_multiplier(health)
        base_budget = float(sleeve.budget_pct_by_regime.get(regime, 0.0) or 0.0)
        budget_pct = round(base_budget * multiplier, 4)

        skip_reason = _sleeve_skip_reason(sleeve, regime, health, budget_pct)
        if skip_reason:
            decisions.append(
                StrategySleeveDecision(
                    name=sleeve.name,
                    role=sleeve.role,
                    status="skipped",
                    regime=regime,
                    budget_pct=0.0,
                    candidate_count=0,
                    selected_count=0,
                    reason=skip_reason,
                    health_alert_level=str(health.get("alert_level", "pass") or "pass"),
                    health_action=str(health.get("action", "keep") or "keep"),
                    exposure_multiplier=multiplier,
                )
            )
            continue

        strategy = sleeve.load_strategy()
        raw = strategy.screen(frame)
        candidates = _prepare_sleeve_candidates(raw, sleeve, regime, budget_pct, config.max_position_pct)
        candidate_frames.append(candidates)
        decisions.append(
            StrategySleeveDecision(
                name=sleeve.name,
                role=sleeve.role,
                status="active",
                regime=regime,
                budget_pct=budget_pct,
                candidate_count=len(raw),
                selected_count=len(candidates),
                reason=_active_reason(sleeve, regime, budget_pct, len(candidates)),
                health_alert_level=str(health.get("alert_level", "pass") or "pass"),
                health_action=str(health.get("action", "keep") or "keep"),
                exposure_multiplier=multiplier,
            )
        )

    combined = _merge_candidate_frames(
        candidate_frames,
        duplicate_vote_bonus=config.duplicate_vote_bonus,
        max_position_pct=config.max_position_pct,
    )
    combined.attrs["selection_strategy_name"] = config.name
    combined.attrs["strategy_portfolio_plan"] = {
        "name": config.name,
        "market_temperature": temperature.to_dict(),
        "sleeves": [item.to_dict() for item in decisions],
    }
    return StrategyPortfolioPlan(config.name, temperature, tuple(decisions), combined)


def apply_portfolio_score_adjustment(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty or "portfolio_score" not in candidates.columns:
        return candidates.copy()
    adjusted = candidates.copy()
    base_score = pd.to_numeric(adjusted.get("score", 0.0), errors="coerce").fillna(0.0)
    portfolio_score = pd.to_numeric(adjusted["portfolio_score"], errors="coerce").fillna(base_score)
    adjusted["score"] = (base_score * 0.75 + portfolio_score * 0.25).round(2)
    sort_columns = ["score"]
    ascending = [False]
    if "portfolio_score" in adjusted.columns:
        sort_columns.append("portfolio_score")
        ascending.append(False)
    if "strategy_vote_count" in adjusted.columns:
        sort_columns.append("strategy_vote_count")
        ascending.append(False)
    return adjusted.sort_values(sort_columns, ascending=ascending).reset_index(drop=True)


def _normalize_temperature(
    frame: pd.DataFrame,
    market_temperature: MarketTemperature | dict[str, Any] | None,
) -> MarketTemperature:
    if isinstance(market_temperature, MarketTemperature):
        return market_temperature
    if isinstance(market_temperature, dict):
        return MarketTemperature(
            score=float(market_temperature.get("score", 0.0) or 0.0),
            regime=str(market_temperature.get("regime", "empty") or "empty"),
            stance=str(market_temperature.get("stance", "") or ""),
            total_symbols=int(market_temperature.get("total_symbols", 0) or 0),
            candidate_count=int(market_temperature.get("candidate_count", 0) or 0),
            advance_ratio=float(market_temperature.get("advance_ratio", 0.0) or 0.0),
            above_ma20_ratio=float(market_temperature.get("above_ma20_ratio", 0.0) or 0.0),
            positive_momentum_ratio=float(market_temperature.get("positive_momentum_ratio", 0.0) or 0.0),
            candidate_ratio=float(market_temperature.get("candidate_ratio", 0.0) or 0.0),
            average_1d_return=float(market_temperature.get("average_1d_return", 0.0) or 0.0),
        )
    return calculate_market_temperature(frame)


def _sleeve_skip_reason(
    sleeve: StrategySleeveConfig,
    regime: str,
    health: dict[str, Any],
    budget_pct: float,
) -> str:
    if not sleeve.enabled:
        return "sleeve disabled"
    if regime not in set(sleeve.enabled_regimes):
        return f"regime {regime} not enabled"
    if _health_blocks_new_positions(health):
        return "strategy health blocks new positions"
    if budget_pct <= 0:
        return f"no budget for regime {regime}"
    return ""


def _prepare_sleeve_candidates(
    raw: pd.DataFrame,
    sleeve: StrategySleeveConfig,
    regime: str,
    budget_pct: float,
    max_position_pct: float,
) -> pd.DataFrame:
    if raw.empty:
        return raw.copy()
    candidates = raw.copy()
    if "score" in candidates.columns and sleeve.min_score is not None:
        candidates = candidates[pd.to_numeric(candidates["score"], errors="coerce").fillna(0.0) >= sleeve.min_score]
    if sleeve.max_candidates:
        candidates = candidates.head(sleeve.max_candidates)
    if candidates.empty:
        return candidates

    candidates = candidates.copy()
    if "symbol" in candidates.columns:
        candidates["symbol"] = candidates["symbol"].astype(str).str.zfill(6)
    candidates["source_strategy"] = sleeve.name
    candidates["strategy_role"] = sleeve.role
    candidates["strategy_market_regime"] = regime
    candidates["strategy_budget_pct"] = budget_pct
    candidates["strategy_score_weight"] = sleeve.score_weight
    candidates["strategy_vote_count"] = 1
    candidates["strategy_votes"] = sleeve.name
    candidates["position_cap_pct"] = round(min(budget_pct / max(len(candidates), 1), max_position_pct), 4)
    base_score = pd.to_numeric(candidates.get("score", 0.0), errors="coerce").fillna(0.0)
    candidates["portfolio_score"] = (base_score * sleeve.score_weight + sleeve.vote_bonus + budget_pct * 20.0).round(4)
    return candidates


def _merge_candidate_frames(
    frames: list[pd.DataFrame],
    *,
    duplicate_vote_bonus: float,
    max_position_pct: float,
) -> pd.DataFrame:
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        empty = pd.DataFrame()
        empty.attrs["selection_strategy_name"] = "adaptive_strategy_portfolio"
        return empty
    data = pd.concat(non_empty, ignore_index=True, sort=False)
    if "symbol" not in data.columns:
        return data.sort_values("portfolio_score", ascending=False).reset_index(drop=True)

    rows: list[pd.Series] = []
    for _, group in data.groupby(data["symbol"].astype(str).str.zfill(6), sort=False):
        ranked = group.sort_values("portfolio_score", ascending=False)
        row = ranked.iloc[0].copy()
        votes = list(dict.fromkeys(str(item) for item in group["source_strategy"].dropna().tolist()))
        row["strategy_votes"] = ",".join(votes)
        row["strategy_vote_count"] = len(votes)
        row["position_cap_pct"] = round(
            min(float(pd.to_numeric(group["position_cap_pct"], errors="coerce").fillna(0.0).sum()), max_position_pct),
            4,
        )
        row["strategy_budget_pct"] = round(float(pd.to_numeric(group["strategy_budget_pct"], errors="coerce").fillna(0.0).sum()), 4)
        row["portfolio_score"] = round(float(row.get("portfolio_score", 0.0) or 0.0) + max(len(votes) - 1, 0) * duplicate_vote_bonus, 4)
        if len(votes) > 1:
            row["reason"] = f"{row.get('reason', '')} | multi-strategy confirmation: {','.join(votes)}".strip()
        rows.append(row)
    merged = pd.DataFrame(rows)
    return merged.sort_values(["portfolio_score", "strategy_vote_count"], ascending=[False, False]).reset_index(drop=True)


def _active_reason(sleeve: StrategySleeveConfig, regime: str, budget_pct: float, selected_count: int) -> str:
    return (
        f"{sleeve.role} sleeve active in {regime}; budget {budget_pct:.1%}; "
        f"selected {selected_count} candidates"
    )


def _normalize_name(value: str) -> str:
    return str(value).strip().lower().replace("-", "_")


def _health_blocks_new_positions(health: dict[str, Any]) -> bool:
    if not health:
        return False
    return str(health.get("alert_level", "pass") or "pass") == "block" or str(health.get("action", "keep") or "keep") == "pause"


def _health_exposure_multiplier(health: dict[str, Any]) -> float:
    if not health:
        return 1.0
    if _health_blocks_new_positions(health):
        return 0.0
    value = health.get("policy_exposure_multiplier")
    if value not in (None, ""):
        return max(0.0, min(float(value), 1.0))
    if str(health.get("alert_level", "pass") or "pass") == "warn" or str(health.get("action", "keep") or "keep") == "reduce":
        return 0.5
    return 1.0
