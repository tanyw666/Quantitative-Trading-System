from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class WeeklyReportInput:
    title: str
    market_temperature: dict | None
    selection_summary: list[dict]
    trade_stats: dict
    notes: list[str]
    gate_summary: list[dict] = field(default_factory=list)


class WeeklyReport:
    def render(self, data: WeeklyReportInput) -> str:
        lines = [
            f"# {data.title}",
            "",
            f"生成日期：{date.today().isoformat()}",
            "",
            "## 1. 市场环境",
            "",
        ]

        if data.market_temperature:
            temp = data.market_temperature
            lines.extend(
                [
                    f"- 市场温度：{float(temp.get('score', 0)):.1f}/100",
                    f"- 市场状态：{temp.get('regime', '')}",
                    f"- 操作建议：{temp.get('stance', '')}",
                    f"- 上涨占比：{float(temp.get('advance_ratio', 0)):.1%}",
                    f"- 站上MA20：{float(temp.get('above_ma20_ratio', 0)):.1%}",
                    "",
                ]
            )
        else:
            lines.extend(["- 暂无市场环境数据。", ""])

        lines.extend(["## 2. 选股后验", ""])
        if data.selection_summary:
            lines.extend(["| 周期 | 样本数 | 平均收益 | 胜率 |", "| --- | ---: | ---: | ---: |"])
            for row in data.selection_summary:
                lines.append(
                    f"| {int(row.get('horizon', 0))}日 | "
                    f"{int(row.get('count', 0))} | "
                    f"{float(row.get('mean_return', 0)):.2%} | "
                    f"{float(row.get('win_rate', 0)):.1%} |"
                )
        else:
            lines.append("- 暂无可验证的历史选股结果。")

        if data.gate_summary:
            lines.extend(["", "按进场闸门：", "", "| 闸门 | 周期 | 样本数 | 平均收益 | 胜率 |", "| --- | ---: | ---: | ---: | ---: |"])
            for row in data.gate_summary:
                lines.append(
                    f"| {row.get('entry_gate', '')} | "
                    f"{int(row.get('horizon', 0))}日 | "
                    f"{int(row.get('count', 0))} | "
                    f"{float(row.get('mean_return', 0)):.2%} | "
                    f"{float(row.get('win_rate', 0)):.1%} |"
                )

        lines.extend(["", "## 3. 交易纪律", ""])
        stats = data.trade_stats
        if stats.get("total_trades", 0):
            lines.extend(
                [
                    f"- 交易笔数：{stats.get('total_trades', 0)}",
                    f"- 买入/卖出：{stats.get('buy_count', 0)} / {stats.get('sell_count', 0)}",
                    f"- 成交总额：{float(stats.get('total_amount', 0)):.2f}",
                    f"- 平均执行偏差：{float(stats.get('avg_execution_deviation_pct', 0)):.2%}",
                    "",
                ]
            )
            mistake_counts = stats.get("mistake_counts", {})
            if mistake_counts:
                lines.append("错误类型：")
                for name, count in mistake_counts.items():
                    lines.append(f"- {name}：{count}")
            tag_counts = stats.get("tag_counts", {})
            if tag_counts:
                lines.append("")
                lines.append("交易标签：")
                for name, count in tag_counts.items():
                    lines.append(f"- {name}：{count}")
        else:
            lines.append("- 暂无交易日志。")

        lines.extend(["", "## 4. 下周改进", ""])
        notes = data.notes or default_weekly_notes(data.selection_summary, stats)
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")
        return "\n".join(lines)


def default_weekly_notes(selection_summary: list[dict], trade_stats: dict) -> list[str]:
    notes: list[str] = []
    summary_frame = pd.DataFrame(selection_summary)
    if not summary_frame.empty and "mean_return" in summary_frame.columns:
        weak = summary_frame[pd.to_numeric(summary_frame["mean_return"], errors="coerce") < 0]
        if not weak.empty:
            notes.append("检查负收益周期的入选条件，避免弱势环境里扩大候选池。")
    if trade_stats.get("mistake_counts"):
        notes.append("优先复盘出现次数最多的错误类型，下周只盯一个纪律问题改。")
    if not notes:
        notes.append("保持记录完整性：每次候选、计划仓位和实际交易都要留痕。")
    return notes
