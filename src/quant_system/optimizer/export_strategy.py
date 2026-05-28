from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_experiment_summary(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def strategy_config_from_summary(
    summary: dict[str, Any],
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    recommendation = summary.get("recommendation")
    if not recommendation:
        raise ValueError("Experiment summary does not contain a recommendation.")

    strategy_name = str(recommendation.get("strategy", "")).strip()
    if not strategy_name:
        raise ValueError("Experiment recommendation is missing strategy name.")

    output_name = name or f"{strategy_name}_recommended"
    output_description = description or (
        f"由实验摘要自动导出的推荐策略。观察周期={summary.get('preferred_horizon', '')}日，"
        f"最小样本={summary.get('min_count', '')}，参数组={recommendation.get('name', '')}"
    )
    return {
        "name": output_name,
        "description": output_description,
        "strategy": strategy_name,
        "params": dict(recommendation.get("params", {}) or {}),
        "scoring_weights": dict(recommendation.get("scoring_weights", {}) or {}),
        "source": {
            "type": "experiment_summary",
            "recommended_case": recommendation.get("name", ""),
            "preferred_horizon": summary.get("preferred_horizon"),
            "min_count": summary.get("min_count"),
            "score": recommendation.get("score"),
        },
    }


def write_strategy_config(path: Path, config: dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to write strategy YAML. Run: python -m pip install -e .[dev]") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
