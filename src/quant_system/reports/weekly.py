from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from quant_system.reports.constraint_summary import render_constraint_summary_lines
from quant_system.reports.action_advice import render_action_advice_lines
from quant_system.reports.discipline_adherence import render_discipline_adherence_lines
from quant_system.reports.discipline_advice import render_discipline_advice_lines
from quant_system.reports.discipline_summary import render_discipline_summary_lines
from quant_system.reports.experiment_summary import render_experiment_summary_lines
from quant_system.reports.gate_review import render_gate_review_lines
from quant_system.reports.promotion_summary import (
    render_promotion_priority_lines,
    render_promotion_summary_lines,
    summarize_promotion_priority,
)
from quant_system.reports.strategy_health import render_strategy_health_lines
from quant_system.reports.strategy_rotation import render_strategy_rotation_lines
from quant_system.reports.rotation_history import render_rotation_history_card_lines
from quant_system.reports.trade_plan_summary import render_trade_plan_summary_lines
from quant_system.portfolio.trade_plan_audit import render_trade_plan_audit_lines
from quant_system.portfolio.action_execution import render_action_execution_lines
from quant_system.portfolio.exit_plan import render_exit_execution_lines, render_exit_plan_lines, render_lot_exit_execution_lines
from quant_system.reports.position_lifecycle import render_position_lifecycle_lines


@dataclass(frozen=True)
class WeeklyReportInput:
    title: str
    market_temperature: dict | None
    selection_summary: list[dict]
    trade_stats: dict
    notes: list[str]
    trade_plan_summary: dict | None = None
    gate_summary: list[dict] = field(default_factory=list)
    experiment_summary: dict | None = None
    promotion_summary: dict | None = None
    strategy_health: list[dict] | None = None
    constraint_summary: dict | None = None
    strategy_rotation: list[dict] | None = None
    rotation_history: dict | None = None
    market_context: dict | None = None
    gate_review: dict | None = None
    discipline_summary: dict | None = None
    discipline_adherence: dict | None = None
    trade_plan_audit: dict | None = None
    action_execution_summary: dict | None = None
    exit_plan: dict | None = None
    exit_execution_summary: dict | None = None
    lot_exit_execution_summary: dict | None = None
    lifecycle_snapshot: dict | None = None


class WeeklyReport:
    def render(self, data: WeeklyReportInput) -> str:
        lines = [
            f"# {data.title}",
            "",
            f"生成日期：{date.today().isoformat()}",
            "",
            "## 0. 今日策略总览",
            "",
        ]

        priority = summarize_promotion_priority(data.experiment_summary, data.promotion_summary)
        lines.extend(render_promotion_priority_lines(data.experiment_summary, data.promotion_summary))
        if priority.get("primary"):
            lines.append(f"- 统一摘要：{priority['primary']}")

        lines.extend(["", "### 策略健康度", ""])
        lines.extend(render_strategy_health_lines(data.strategy_health))

        lines.extend(["", "### 策略约束复盘", ""])
        lines.extend(render_constraint_summary_lines(data.constraint_summary))

        lines.extend(["", "### 策略轮换建议", ""])
        lines.extend(render_strategy_rotation_lines(data.strategy_rotation))

        lines.extend(["", "### 策略轮换历史", ""])
        lines.extend(render_rotation_history_card_lines(data.rotation_history))

        lines.extend(["", "## 1. 市场环境", ""])
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

        if data.market_context:
            lines.extend(["## 1.1 真实市场上下文", ""])
            for item in data.market_context.get("summary_lines", []) or ["- 暂无真实市场上下文。"]:
                lines.append(item)

        lines.extend(["", "## 2. 选股回验", ""])
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

        lines.extend(["", "## 3. 策略实验", ""])
        lines.extend(render_experiment_summary_lines(data.experiment_summary))

        lines.extend(["", "## 4. 策略晋升", ""])
        lines.extend(render_promotion_summary_lines(data.promotion_summary))

        lines.extend(["", "## 5. 交易纪律", ""])
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
            gate_counts = stats.get("gate_counts", {})
            if gate_counts:
                lines.append("")
                lines.append("盘前门禁：")
                for name, count in gate_counts.items():
                    lines.append(f"- {gate_status_label(name)}：{count}")
                if int(stats.get("gate_violation_count", 0) or 0):
                    lines.append(f"- 预警/阻断状态下买入：{int(stats.get('gate_violation_count', 0))} 笔")
        else:
            lines.append("- 暂无交易日志。")

        lines.extend(["", "## 6. 下周改进", ""])
        lines.extend(["", "### Gate Discipline", ""])
        lines.extend(render_gate_review_lines(data.gate_review))
        lines.extend(["", "### 交易计划单", ""])
        lines.extend(render_trade_plan_summary_lines(data.trade_plan_summary))
        lines.extend(["", "### Discipline Advice", ""])
        lines.extend(
            render_discipline_advice_lines(
                gate_review=data.gate_review,
                trade_stats=stats,
            )
        )
        lines.extend(["", "### 计划-成交审计", ""])
        lines.extend(render_trade_plan_audit_lines(data.trade_plan_audit))
        lines.extend(["", "### 持仓动作执行审计", ""])
        lines.extend(render_action_execution_lines(data.action_execution_summary))
        lines.extend(["", "### Exit Plan", ""])
        lines.extend(render_exit_plan_lines(data.exit_plan))
        lines.extend(["", "### Exit Execution Audit", ""])
        lines.extend(render_exit_execution_lines(data.exit_execution_summary))
        lines.extend(["", "### Lot Exit Execution Audit", ""])
        lines.extend(render_lot_exit_execution_lines(data.lot_exit_execution_summary))
        lines.extend(["", "### Position Lifecycle", ""])
        lines.extend(render_position_lifecycle_lines(data.lifecycle_snapshot))

        lines.extend(["", "### Discipline History", ""])
        lines.extend(render_discipline_summary_lines(data.discipline_summary))

        lines.extend(["", "### Discipline Adherence", ""])
        lines.extend(render_discipline_adherence_lines(data.discipline_adherence))

        lines.extend(["", "## 7. 下周动作建议", ""])
        lines.extend(
            render_action_advice_lines(
                strategy_health=data.strategy_health,
                constraint_summary=data.constraint_summary,
                trade_plan_audit=data.trade_plan_audit,
                market_temperature=data.market_temperature,
                exit_plan=data.exit_plan,
            )
        )

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
            notes.append("先修复负收益周期的入选条件，弱势环境里不要硬扩候选池。")
    if trade_stats.get("mistake_counts"):
        notes.append("优先复盘出现次数最多的错误类型，下周只盯一个纪律问题改。")
    if int(trade_stats.get("gate_violation_count", 0) or 0):
        notes.append("复盘所有盘前门禁预警/阻断下的买入，确认是否违反计划纪律。")
    if not notes:
        notes.append("保持记录完整：每次候选、计划仓位和实际交易都要留痕。")
    return notes


def gate_status_label(status: str) -> str:
    return {"pass": "通过", "warn": "预警", "block": "阻断"}.get(str(status), str(status))
