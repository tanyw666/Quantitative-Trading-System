from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from quant_system.optimizer.selection_validation import summarize_forward_returns, validate_selections
from quant_system.screening.scoring import score_candidates
from quant_system.strategies.dragon_leader import DragonLeaderStrategy
from quant_system.strategies.strong_stock_screen import StrongStockScreen


@dataclass(frozen=True)
class ExperimentCase:
    name: str
    strategy: str = "strong_stock_screen"
    params: dict[str, Any] = field(default_factory=dict)
    scoring_weights: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ExperimentResult:
    name: str
    strategy: str
    params: dict[str, Any]
    scoring_weights: dict[str, float]
    selection_count: int
    summary: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


def preset_cases(name: str) -> list[ExperimentCase]:
    normalized = name.strip().lower().replace("-", "_")
    if normalized == "strong_stock_basic":
        return [
            ExperimentCase(
                name="conservative",
                params={"min_20d_return": 0.18, "min_volume_ratio": 1.8, "max_atr_pct": 0.08},
                scoring_weights={"momentum_20": 0.45, "volume_ratio_20": 0.25, "atr_pct_14": 0.30},
            ),
            ExperimentCase(
                name="balanced",
                params={"min_20d_return": 0.12, "min_volume_ratio": 1.5, "max_atr_pct": 0.12},
                scoring_weights={"momentum_20": 0.50, "volume_ratio_20": 0.30, "atr_pct_14": 0.20},
            ),
            ExperimentCase(
                name="aggressive",
                params={"min_20d_return": 0.08, "min_volume_ratio": 1.2, "max_atr_pct": 0.16},
                scoring_weights={"momentum_20": 0.60, "volume_ratio_20": 0.30, "atr_pct_14": 0.10},
            ),
        ]
    if normalized == "dragon_next_open_gap":
        return [
            ExperimentCase(
                name=f"gap_hi_{hi:.2f}_lo_{lo:.2f}",
                strategy="dragon_leader",
                params={
                    "entry_gate": "pass",
                    "entry_model": "next_open",
                    "max_next_open_gap": hi,
                    "min_next_open_gap": lo,
                },
            )
            for hi in (0.03, 0.05, 0.07, 0.10)
            for lo in (-0.01, -0.03, -0.05)
        ]
    raise ValueError(f"Unknown experiment preset: {name}")


def load_experiment_cases(path: Path) -> list[ExperimentCase]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load experiment YAML. Run: python -m pip install -e .[dev]") from exc

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or []
    return experiment_cases_from_mapping(raw)


def experiment_cases_from_mapping(raw: Any) -> list[ExperimentCase]:
    if isinstance(raw, dict):
        raw = raw.get("cases", [])
    if not isinstance(raw, list):
        raise ValueError("Experiment config must contain a list or a mapping with a cases list")
    return [ExperimentCase(**item) for item in raw]


def run_parameter_experiments(
    frame: pd.DataFrame,
    cases: list[ExperimentCase],
    horizons: tuple[int, ...] = (1, 3, 5),
    top: int = 5,
    min_history: int = 25,
) -> list[ExperimentResult]:
    results: list[ExperimentResult] = []
    for case in cases:
        selections = walk_forward_selections(frame, case, top=top, min_history=min_history)
        validation = validate_selections(selections, frame, horizons=horizons)
        summary = summarize_forward_returns(pd.DataFrame([item.to_dict() for item in validation]))
        results.append(
            ExperimentResult(
                name=case.name,
                strategy=case.strategy,
                params=case.params,
                scoring_weights=case.scoring_weights,
                selection_count=len(selections),
                summary=summary.to_dict(orient="records"),
            )
        )
    return results


def walk_forward_selections(
    frame: pd.DataFrame,
    case: ExperimentCase,
    top: int = 5,
    min_history: int = 25,
) -> list[dict]:
    data = frame.copy()
    if "symbol" not in data.columns:
        data["symbol"] = "SINGLE"
    data["date"] = pd.to_datetime(data["date"])
    dates = sorted(data["date"].dropna().unique())
    strategy = build_experiment_strategy(case)

    selections: list[dict] = []
    for current_date in dates:
        history = data[data["date"] <= current_date]
        if history.groupby("symbol")["date"].count().max() < min_history:
            continue
        selected = strategy.screen(history)
        if selected.empty:
            continue
        if case.scoring_weights:
            selected = score_candidates(selected, case.scoring_weights)
        selected = selected.head(top)
        for row in selected.to_dict(orient="records"):
            selections.append(
                {
                    "date": str(row.get("date", ""))[:10],
                    "symbol": str(row.get("symbol", "SINGLE")),
                    "strategy": case.name,
                    "close": float(row.get("close", 0.0)),
                    "entry_gate": str(row.get("entry_gate", "")),
                    "dragon_state": str(row.get("dragon_state", "")),
                    "dragon_tags": str(row.get("dragon_tags", "")),
                    "dragon_score": float(row.get("dragon_score", 0.0) or 0.0),
                    "seal_quality_score": float(row.get("seal_quality_score", 0.0) or 0.0),
                }
            )
    return selections


def build_experiment_strategy(case: ExperimentCase):
    normalized = case.strategy.strip().lower().replace("-", "_")
    if normalized == "strong_stock_screen":
        return StrongStockScreen(**case.params)
    if normalized == "dragon_leader":
        return DragonLeaderStrategy(**case.params)
    raise ValueError(f"Unsupported experiment strategy: {case.strategy}")
