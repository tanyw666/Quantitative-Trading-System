from __future__ import annotations


def render_experiment_summary_lines(summary: dict | None) -> list[str]:
    if not summary:
        return ["- 暂无策略实验摘要。"]

    recommendation = summary.get("recommendation")
    lines = [
        f"- 推荐参考周期：{int(summary.get('preferred_horizon', 0))}日",
        f"- 推荐样本门槛：{int(summary.get('min_count', 0))}",
        f"- 实验组数量：{int(summary.get('result_count', 0))}",
    ]
    if not recommendation:
        lines.append("- 暂无满足门槛的推荐参数组。")
        return lines

    params = recommendation.get("params", {}) or {}
    params_text = ", ".join(f"{key}={value}" for key, value in params.items()) or "无"
    lines.extend(
        [
            f"- 推荐参数组：{recommendation.get('name', '')}",
            f"- 策略：{recommendation.get('strategy', '')}",
            f"- 参数：{params_text}",
        ]
    )
    if "mean_return" in recommendation:
        lines.append(f"- 平均收益：{float(recommendation.get('mean_return', 0)):.2%}")
    if "win_rate" in recommendation:
        lines.append(f"- 胜率：{float(recommendation.get('win_rate', 0)):.1%}")
    if "count" in recommendation:
        lines.append(f"- 样本数：{int(recommendation.get('count', 0))}")
    if "score" in recommendation:
        lines.append(f"- 稳健评分：{float(recommendation.get('score', 0)):.4f}")
    if recommendation.get("reason"):
        lines.append(f"- 推荐原因：{recommendation.get('reason')}")
    return lines


def render_experiment_summary_lines(summary: dict | None) -> list[str]:
    if not summary:
        return ["- 暂无策略实验摘要。"]

    recommendation = summary.get("recommendation")
    lines = [
        f"- 推荐参考周期：{int(summary.get('preferred_horizon', 0))}日",
        f"- 推荐样本门槛：{int(summary.get('min_count', 0))}",
        f"- 实验组数量：{int(summary.get('result_count', 0))}",
    ]
    if not recommendation:
        lines.append("- 暂无满足门槛的推荐参数组。")
        return lines

    params = recommendation.get("params", {}) or {}
    params_text = ", ".join(f"{key}={value}" for key, value in params.items()) or "无"
    lines.extend(
        [
            f"- 推荐参数组：{recommendation.get('name', '')}",
            f"- 策略：{recommendation.get('strategy', '')}",
            f"- 参数：{params_text}",
        ]
    )
    if "mean_return" in recommendation:
        lines.append(f"- 平均收益：{float(recommendation.get('mean_return', 0)):.2%}")
    if "win_rate" in recommendation:
        lines.append(f"- 胜率：{float(recommendation.get('win_rate', 0)):.1%}")
    if "count" in recommendation:
        lines.append(f"- 样本数：{int(recommendation.get('count', 0))}")
    if "score" in recommendation:
        lines.append(f"- 稳健评分：{float(recommendation.get('score', 0)):.4f}")
    if recommendation.get("reason"):
        lines.append(f"- 推荐原因：{recommendation.get('reason')}")
    return lines
