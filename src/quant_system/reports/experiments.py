from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date


@dataclass(frozen=True)
class ExperimentRecommendation:
    name: str
    strategy: str
    params: dict
    scoring_weights: dict
    horizon: int
    mean_return: float
    win_rate: float
    count: int
    score: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class ExperimentReport:
    def __init__(self, preferred_horizon: int = 3, min_count: int = 5) -> None:
        self.preferred_horizon = preferred_horizon
        self.min_count = min_count

    def render(self, results: list[dict]) -> str:
        recommendation = recommend_experiment(
            results,
            preferred_horizon=self.preferred_horizon,
            min_count=self.min_count,
        )
        lines = [
            "# 策略参数实验报告",
            "",
            f"生成日期：{date.today().isoformat()}",
            "",
            "## 1. 推荐结论",
            "",
        ]
        if recommendation:
            params = ", ".join(f"{key}={value}" for key, value in recommendation.params.items()) or "无"
            lines.extend(
                [
                    f"- 推荐参数组：{recommendation.name}",
                    f"- 策略：{recommendation.strategy}",
                    f"- 参数：{params}",
                    f"- 参考周期：{recommendation.horizon}日",
                    f"- 平均收益：{recommendation.mean_return:.2%}",
                    f"- 胜率：{recommendation.win_rate:.1%}",
                    f"- 样本数：{recommendation.count}",
                    f"- 稳健评分：{recommendation.score:.4f}",
                    f"- 推荐原因：{recommendation.reason}",
                    "",
                ]
            )
        else:
            lines.extend(["- 暂无满足样本数门槛的实验结果。", ""])

        lines.extend(
            [
                "## 2. 实验明细",
                "",
                "| 参数组 | 周期 | 样本数 | 平均收益 | 胜率 | 参数 |",
                "| --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for result in results:
            params = ", ".join(f"{key}={value}" for key, value in result.get("params", {}).items())
            for row in result.get("summary", []):
                lines.append(
                    f"| {result.get('name', '')} | "
                    f"{int(row.get('horizon', 0))}日 | "
                    f"{int(row.get('count', 0))} | "
                    f"{float(row.get('mean_return', 0)):.2%} | "
                    f"{float(row.get('win_rate', 0)):.1%} | "
                    f"{params} |"
                )

        lines.extend(["", "## 3. 使用提醒", ""])
        lines.append(f"- 当前推荐门槛：优先参考 {self.preferred_horizon} 日周期，至少 {self.min_count} 个有效样本。")
        lines.append("- 优先选择样本数足够、收益和胜率都稳定的参数组，不要只看最高收益。")
        lines.append("- 参数实验是研究工具，不代表未来收益保证。")
        lines.append("")
        return "\n".join(lines)


def recommend_experiment(
    results: list[dict],
    preferred_horizon: int = 3,
    min_count: int = 5,
) -> ExperimentRecommendation | None:
    candidates = []
    for result in results:
        for row in result.get("summary", []):
            candidates.append(
                {
                    "name": result.get("name", ""),
                    "strategy": result.get("strategy", ""),
                    "params": dict(result.get("params", {})),
                    "scoring_weights": dict(result.get("scoring_weights", {})),
                    "horizon": int(row.get("horizon", 0)),
                    "mean_return": float(row.get("mean_return", 0)),
                    "win_rate": float(row.get("win_rate", 0)),
                    "count": int(row.get("count", 0)),
                }
            )
    if not candidates:
        return None

    horizons = {int(item["horizon"]) for item in candidates}
    target_horizon = preferred_horizon if preferred_horizon in horizons else max(horizons)
    candidates = [
        item for item in candidates if int(item["horizon"]) == target_horizon and int(item["count"]) >= min_count
    ]
    if not candidates:
        return None

    def robust_score(item: dict) -> float:
        sample_bonus = min(int(item["count"]), 50) * 0.0001
        win_rate_bonus = (float(item["win_rate"]) - 0.5) * 0.01
        return float(item["mean_return"]) + win_rate_bonus + sample_bonus

    best = sorted(
        candidates,
        key=lambda item: (robust_score(item), item["mean_return"], item["win_rate"], item["count"]),
        reverse=True,
    )[0]
    return ExperimentRecommendation(
        name=str(best["name"]),
        strategy=str(best["strategy"]),
        params=dict(best["params"]),
        scoring_weights=dict(best["scoring_weights"]),
        horizon=int(best["horizon"]),
        mean_return=float(best["mean_return"]),
        win_rate=float(best["win_rate"]),
        count=int(best["count"]),
        score=robust_score(best),
        reason=f"按{target_horizon}日周期筛选，样本数不少于{min_count}，综合平均收益、胜率和样本规模排序。",
    )


def build_experiment_summary_payload(
    results: list[dict],
    preferred_horizon: int = 3,
    min_count: int = 5,
) -> dict:
    recommendation = recommend_experiment(
        results,
        preferred_horizon=preferred_horizon,
        min_count=min_count,
    )
    return {
        "generated_at": date.today().isoformat(),
        "preferred_horizon": preferred_horizon,
        "min_count": min_count,
        "recommendation": recommendation.to_dict() if recommendation else None,
        "result_count": len(results),
    }
