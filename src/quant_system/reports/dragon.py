from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DragonValidationInput:
    title: str
    entry_gate: str
    entry_model: str
    buy_price: str
    signal_summary: list[dict]
    gate_summary: list[dict]
    backtest_summary: dict
    candidates: list[dict] | None = None


class DragonValidationReport:
    def render(self, data: DragonValidationInput) -> str:
        lines = [
            f"# {data.title}",
            "",
            f"生成日期：{date.today().isoformat()}",
            "",
            "## 1. 当前龙头候选",
            "",
        ]
        if data.candidates:
            lines.extend(["| 代码 | 名称 | 收盘 | 龙头分 | 封板质量 | 闸门 | 状态 | 标签 |", "| --- | --- | ---: | ---: | ---: | --- | --- | --- |"])
            for item in data.candidates:
                lines.append(
                    f"| {item.get('symbol', '')} | "
                    f"{item.get('name', '')} | "
                    f"{float(item.get('close', 0)):.2f} | "
                    f"{float(item.get('dragon_score', item.get('score', 0))):.1f} | "
                    f"{float(item.get('seal_quality_score', 0)):.1f} | "
                    f"{item.get('entry_gate', '')} | "
                    f"{item.get('dragon_state', '')} | "
                    f"{item.get('dragon_tags', '')} |"
                )
        else:
            lines.append("- 当前没有龙头候选，或尚未运行 dragon screen。")

        lines.extend(["", "## 2. 信号后验", ""])
        if data.signal_summary:
            lines.extend(["| 周期 | 样本数 | 平均收益 | 胜率 |", "| --- | ---: | ---: | ---: |"])
            for row in data.signal_summary:
                lines.append(_summary_row(row))
        else:
            lines.append("- 暂无可验证信号。先用 `dragon screen --record` 记录候选，再积累后验样本。")

        lines.extend(["", "## 3. 按进场闸门", ""])
        if data.gate_summary:
            lines.extend(["| 闸门 | 周期 | 样本数 | 平均收益 | 胜率 |", "| --- | ---: | ---: | ---: | ---: |"])
            for row in data.gate_summary:
                lines.append(
                    f"| {row.get('entry_gate', '')} | "
                    f"{int(row.get('horizon', 0))}日 | "
                    f"{int(row.get('count', 0))} | "
                    f"{float(row.get('mean_return', 0)):.2%} | "
                    f"{float(row.get('win_rate', 0)):.1%} |"
                )
        else:
            lines.append("- 暂无带 entry_gate 的历史信号。")

        summary = data.backtest_summary
        lines.extend(
            [
                "",
                "## 4. 可成交回测",
                "",
                f"- 回测闸门：{data.entry_gate}",
                f"- 买点模型：{data.entry_model}",
                f"- 买入价格：{data.buy_price}",
                f"- 总收益：{float(summary.get('total_return', 0)):.2%}",
                f"- 最终权益：{float(summary.get('final_equity', 0)):.2f}",
                f"- 最大回撤：{float(summary.get('max_drawdown', 0)):.2%}",
                f"- 交易次数：{int(summary.get('trades', 0))}",
                f"- 胜率：{float(summary.get('win_rate', 0)):.1%}",
                "",
                "## 5. 结论提示",
                "",
            ]
        )
        lines.extend(_notes(data))
        lines.append("")
        return "\n".join(lines)


def _summary_row(row: dict) -> str:
    return (
        f"| {int(row.get('horizon', 0))}日 | "
        f"{int(row.get('count', 0))} | "
        f"{float(row.get('mean_return', 0)):.2%} | "
        f"{float(row.get('win_rate', 0)):.1%} |"
    )


def _notes(data: DragonValidationInput) -> list[str]:
    notes: list[str] = []
    if not data.signal_summary:
        notes.append("- 信号样本不足，先记录候选再判断闸门质量。")
    if int(data.backtest_summary.get("trades", 0)) == 0:
        notes.append("- 可成交回测没有交易时，重点检查是否被涨停买入约束或进场闸门拦截。")
    if data.gate_summary:
        notes.append("- 优先比较 pass/watch/block 的后验收益差异，再决定是否收紧闸门。")
    if data.candidates:
        notes.append("- 当前候选只代表技术结构信号，仍需叠加流动性、公告和题材确认。")
    return notes or ["- 信号后验和可成交回测都正常，继续扩大样本验证。"]
