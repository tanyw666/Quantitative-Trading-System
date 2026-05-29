from __future__ import annotations

from quant_system.reports.trade_plan_pressure import format_trade_plan_pressure, normalize_trade_plan_pressure


def render_promotion_summary_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("total", 0)) == 0:
        return ["- 暂无策略晋升历史。"]

    lines = [
        f"- 晋升记录：{int(summary.get('total', 0))} 条",
        f"- 成功/失败：{int(summary.get('ok_count', 0))} / {int(summary.get('failed_count', 0))}",
        f"- 已回测：{int(summary.get('backtest_count', 0))} 条",
    ]
    latest = summary.get("latest_created_at")
    if latest:
        lines.append(f"- 最近晋升：{latest}")

    pressure = normalize_trade_plan_pressure(summary)
    if pressure:
        lines.append(f"- 计划压力：{format_trade_plan_pressure(pressure)}")

    best = summary.get("best_backtest")
    if best:
        lines.extend(
            [
                "- 最佳回测晋升："
                f"{best.get('output', '')}，"
                f"总收益 {float(best.get('total_return', 0)):.2%}，"
                f"Sharpe {float(best.get('sharpe', 0)):.2f}，"
                f"交易 {int(best.get('trades', 0))} 笔",
            ]
        )

    records = summary.get("records", []) or []
    if records:
        lines.extend(["", "| 时间 | 策略配置 | 状态 | 回测收益 | Sharpe | 计划压力 |", "| --- | --- | --- | ---: | ---: | --- |"])
        for record in records:
            status = "通过" if record.get("ok") else "失败"
            total_return = record.get("total_return")
            sharpe = record.get("sharpe")
            total_return_text = f"{float(total_return):.2%}" if total_return is not None else "-"
            sharpe_text = f"{float(sharpe):.2f}" if sharpe is not None else "-"
            pressure = _pressure_text(record)
            lines.append(
                f"| {record.get('created_at', '')} | "
                f"{record.get('output', '')} | "
                f"{status} | "
                f"{total_return_text} | "
                f"{sharpe_text} | "
                f"{pressure} |"
            )
    return lines


def render_promotion_priority_lines(
    experiment_summary: dict | None,
    promotion_summary: dict | None,
) -> list[str]:
    lines: list[str] = []
    recommendation = (experiment_summary or {}).get("recommendation") or {}
    best_backtest = (promotion_summary or {}).get("best_backtest") or {}
    pressure = normalize_trade_plan_pressure(promotion_summary)

    if best_backtest:
        lines.append(
            f"- 优先观察：{best_backtest.get('output', '')}，"
            f"总收益 {float(best_backtest.get('total_return', 0)):.2%}，"
            f"Sharpe {float(best_backtest.get('sharpe', 0)):.2f}"
        )
    elif recommendation:
        lines.append(
            f"- 优先观察：{recommendation.get('strategy', '')} / {recommendation.get('name', '')}，"
            f"参考收益 {float(recommendation.get('mean_return', 0)):.2%}，"
            f"Sharpe {float(recommendation.get('score', 0)):.4f}"
        )
    else:
        lines.append("- 暂无可优先观察的策略。")

    if best_backtest and recommendation:
        lines.append(
            "- 对照实验推荐："
            f"{recommendation.get('strategy', '')} / {recommendation.get('name', '')}"
        )
    if pressure:
        lines.append(f"- 计划压力：{format_trade_plan_pressure(pressure)}")
    latest = (promotion_summary or {}).get("latest_created_at")
    if latest:
        lines.append(f"- 最近晋升时间：{latest}")
    return lines


def summarize_promotion_priority(
    experiment_summary: dict | None,
    promotion_summary: dict | None,
) -> dict[str, str | None]:
    recommendation = (experiment_summary or {}).get("recommendation") or {}
    best_backtest = (promotion_summary or {}).get("best_backtest") or {}
    latest = (promotion_summary or {}).get("latest_created_at")
    pressure = normalize_trade_plan_pressure(promotion_summary)

    if best_backtest:
        primary = str(best_backtest.get("output", ""))
        reason = (
            f"总收益 {float(best_backtest.get('total_return', 0)):.2%}，"
            f"Sharpe {float(best_backtest.get('sharpe', 0)):.2f}"
        )
    elif recommendation:
        primary = f"{recommendation.get('strategy', '')} / {recommendation.get('name', '')}"
        reason = (
            f"参考收益 {float(recommendation.get('mean_return', 0)):.2%}，"
            f"score {float(recommendation.get('score', 0)):.4f}"
        )
    else:
        primary = ""
        reason = "暂无可优先观察的策略。"

    if pressure:
        reason = f"{reason}，{format_trade_plan_pressure(pressure)}"

    return {
        "primary": primary,
        "reason": reason,
        "latest_created_at": latest,
        "recommended_case": str(recommendation.get("name", "")) if recommendation else "",
    }


def _pressure_text(record: dict) -> str:
    pressure = record.get("trade_plan_pressure") or {}
    if not pressure:
        return "-"
    return (
        f"{float(pressure.get('score', 0) or 0):.1f}/"
        f"{str(pressure.get('status', '') or '-')}"
    )
