from __future__ import annotations


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
        lines.extend(["", "| 时间 | 策略配置 | 状态 | 回测收益 | Sharpe |", "| --- | --- | --- | ---: | ---: |"])
        for record in records:
            status = "通过" if record.get("ok") else "失败"
            total_return = record.get("total_return")
            sharpe = record.get("sharpe")
            total_return_text = f"{float(total_return):.2%}" if total_return is not None else "-"
            sharpe_text = f"{float(sharpe):.2f}" if sharpe is not None else "-"
            lines.append(
                f"| {record.get('created_at', '')} | "
                f"{record.get('output', '')} | "
                f"{status} | "
                f"{total_return_text} | "
                f"{sharpe_text} |"
            )
    return lines
