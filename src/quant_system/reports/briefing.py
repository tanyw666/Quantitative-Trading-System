from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quant_system.reports.action_advice import render_action_advice_lines
from quant_system.reports.constraint_summary import render_constraint_summary_lines
from quant_system.reports.discipline_adherence import render_discipline_adherence_lines
from quant_system.reports.daily import render_data_health_lines
from quant_system.reports.discipline_advice import render_discipline_advice_lines
from quant_system.reports.discipline_summary import render_discipline_summary_lines
from quant_system.reports.experiment_summary import render_experiment_summary_lines
from quant_system.reports.gate_review import render_gate_review_lines
from quant_system.reports.promotion_summary import (
    render_promotion_priority_lines,
    render_promotion_summary_lines,
    summarize_promotion_priority,
)
from quant_system.reports.pretrade import render_precheck_summary_lines
from quant_system.reports.strategy_health import render_strategy_health_lines
from quant_system.reports.strategy_rotation import render_strategy_rotation_lines
from quant_system.reports.rotation_history import render_rotation_history_card_lines


@dataclass(frozen=True)
class BriefingInput:
    title: str
    market_temperature: dict
    candidates: list[dict]
    allocation_plan: dict
    position_book: dict
    holding_risk: dict
    dragon_candidates: list[dict] | None = None
    sectors: list[dict] | None = None
    experiment_summary: dict | None = None
    promotion_summary: dict | None = None
    strategy_health: list[dict] | None = None
    constraint_summary: dict | None = None
    strategy_rotation: list[dict] | None = None
    rotation_history: dict | None = None
    pretrade_checks: list[dict] | None = None
    market_context: dict | None = None
    data_health: dict | None = None
    gate_review: dict | None = None
    trade_stats: dict | None = None
    discipline_summary: dict | None = None
    discipline_adherence: dict | None = None


class BriefingReport:
    def render(self, data: BriefingInput) -> str:
        lines = [
            f"# {data.title}",
            "",
            f"生成日期：{date.today().isoformat()}",
            "",
            "## 0. 今日策略总览",
            "",
            "## 策略优先级",
            "",
        ]

        priority = summarize_promotion_priority(data.experiment_summary, data.promotion_summary)
        lines.extend(render_promotion_priority_lines(data.experiment_summary, data.promotion_summary))
        if priority.get("primary"):
            lines.append(f"- 统一摘要：{priority['primary']}")

        lines.extend(["", "## 策略健康度", ""])
        lines.extend(render_strategy_health_lines(data.strategy_health))

        lines.extend(["", "## 策略约束复盘", ""])
        lines.extend(render_constraint_summary_lines(data.constraint_summary))

        lines.extend(["", "## 策略轮换建议", ""])
        lines.extend(render_strategy_rotation_lines(data.strategy_rotation))

        lines.extend(["", "## 策略轮换历史", ""])
        lines.extend(render_rotation_history_card_lines(data.rotation_history))

        lines.extend(["", "## 1. 市场温度", ""])
        temp = data.market_temperature
        lines.extend(
            [
                f"- 温度：{float(temp.get('score', 0)):.1f}/100",
                f"- 状态：{temp.get('regime', '')}",
                f"- 建议：{temp.get('stance', '')}",
                f"- 上涨占比：{float(temp.get('advance_ratio', 0)):.1%}",
                f"- 站上MA20：{float(temp.get('above_ma20_ratio', 0)):.1%}",
            ]
        )

        if data.market_context:
            lines.extend(["", "## 1.1 真实市场上下文", ""])
            for item in data.market_context.get("summary_lines", []) or ["- 暂无真实市场上下文。"]:
                lines.append(item)

        if data.data_health:
            lines.extend(["", "## 1.2 数据健康", ""])
            lines.extend(render_data_health_lines(data.data_health))

        lines.extend(["", "## 2. 今日候选", ""])
        if data.candidates:
            for item in data.candidates:
                dragon_note = candidate_dragon_note(item)
                lines.append(
                    f"- {item.get('symbol', '')} {item.get('name', '')}："
                    f"评分 {float(item.get('score', 0)):.1f}，"
                    f"风险 {item.get('risk_grade', '')}，"
                    f"收盘 {item.get('close', '')}{dragon_note}"
                )
        else:
            lines.append("- 暂无候选。")

        lines.extend(["", "## 2.1 龙头验证", ""])
        if data.dragon_candidates:
            for item in data.dragon_candidates:
                tags = str(item.get("dragon_tags", "")).replace(",", "/")
                lines.append(
                    f"- {item.get('symbol', '')} {item.get('name', '')}："
                    f"龙头分 {float(item.get('dragon_score', item.get('score', 0))):.1f}，"
                    f"封板质量 {float(item.get('seal_quality_score', 0)):.1f}，"
                    f"闸门 {item.get('entry_gate', '')}，"
                    f"状态 {item.get('dragon_state', '')}"
                    f"{f'，标签 {tags}' if tags else ''}"
                )
        else:
            lines.append("- 暂无龙头候选。")

        lines.extend(["", "## 3. 主线板块", ""])
        if data.sectors:
            for item in data.sectors:
                lines.append(
                    f"- {item.get('sector', '')}："
                    f"强度 {float(item.get('strength_score', 0)):.1f}，"
                    f"候选 {int(item.get('candidate_count', 0))}，"
                    f"20日动量 {float(item.get('avg_momentum_20', 0)):.2%}"
                )
        else:
            lines.append("- 暂无板块字段，无法识别主线。")

        lines.extend(["", "## 4. 策略参数参考", ""])
        lines.extend(render_experiment_summary_lines(data.experiment_summary))

        lines.extend(["", "## 5. 策略晋升", ""])
        lines.extend(render_promotion_summary_lines(data.promotion_summary))

        plan = data.allocation_plan
        lines.extend(
            [
                "",
                "## 6. 仓位计划",
                "",
                *([f"- 策略约束：{plan.get('strategy_adjustment_note')}"] if plan.get("strategy_adjustment_note") else []),
                f"- 目标总仓位：{float(plan.get('target_exposure_pct', 0)):.1%}",
                f"- 已分配仓位：{float(plan.get('allocated_pct', 0)):.1%}",
            ]
        )
        for item in plan.get("items", []):
            lines.append(
                f"- {item.get('symbol', '')} {item.get('name', '')}："
                f"{float(item.get('target_pct', 0)):.1%}，"
                f"资金 {float(item.get('target_value', 0)):.2f}"
            )

        lines.extend(["", "## 6.1 交易前预检预览", ""])
        lines.extend(render_precheck_summary_lines(data.pretrade_checks))

        lines.extend(["", "## 6.2 Gate Discipline", ""])
        lines.extend(render_gate_review_lines(data.gate_review))
        lines.extend(["", "## 6.3 Discipline Advice", ""])
        lines.extend(
            render_discipline_advice_lines(
                gate_review=data.gate_review,
                trade_stats=data.trade_stats,
                holding_risk=data.holding_risk,
                allocation_plan=data.allocation_plan,
            )
        )

        lines.extend(["", "## 6.4 Discipline History", ""])
        lines.extend(render_discipline_summary_lines(data.discipline_summary))

        lines.extend(["", "## 6.5 Discipline Adherence", ""])
        lines.extend(render_discipline_adherence_lines(data.discipline_adherence))

        book = data.position_book
        lines.extend(
            [
                "",
                "## 7. 当前持仓",
                "",
                f"- 总市值：{float(book.get('total_market_value', 0)):.2f}",
                f"- 总浮盈亏：{float(book.get('total_unrealized_pnl', 0)):.2f}",
                f"- 总暴露：{float(book.get('total_exposure_pct', 0)):.1%}",
            ]
        )
        positions = book.get("positions", [])
        if positions:
            for position in positions:
                pnl = position.get("unrealized_pnl")
                pnl_text = f"，浮盈亏 {float(pnl):.2f}" if pnl is not None else ""
                lines.append(
                    f"- {position.get('symbol', '')} {position.get('name', '')}："
                    f"{int(position.get('quantity', 0))} 股，"
                    f"成本 {float(position.get('avg_cost', 0)):.2f}{pnl_text}"
                )
        else:
            lines.append("- 当前无持仓。")

        risk = data.holding_risk
        lines.extend(["", "## 8. 风险检查", "", f"- 总状态：{risk.get('status', '')}"])
        for check in risk.get("checks", []):
            lines.append(f"- [{check.get('status', '')}] {check.get('message', '')}")

        lines.extend(["", "## 9. 今日动作", ""])
        lines.extend(
            render_action_advice_lines(
                strategy_health=data.strategy_health,
                constraint_summary=data.constraint_summary,
                allocation_plan=data.allocation_plan,
                market_temperature=temp,
            )
        )
        lines.append("")
        return "\n".join(lines)


def action_notes(market_temperature: dict, candidates: list[dict], holding_risk: dict) -> list[str]:
    notes: list[str] = []
    risk_status = holding_risk.get("status", "pass")
    regime = market_temperature.get("regime", "empty")
    if risk_status == "block":
        notes.append("- 先处理持仓风险，暂停新增仓位。")
    elif regime in {"frozen", "cold"}:
        notes.append("- 市场偏弱，优先观察，减少新开仓。")
    elif candidates:
        notes.append("- 只从高评分候选中挑选，买入前必须先做 precheck。")
    else:
        notes.append("- 无候选，不做强行交易。")
    notes.append("- 所有实际交易必须写入 review/trade-add，盘后复盘执行偏差。")
    return notes


def candidate_dragon_note(item: dict) -> str:
    if "dragon_score" not in item:
        return ""
    tags = str(item.get("dragon_tags", "")).replace(",", "/")
    return (
        f" | dragon {float(item.get('dragon_score', 0)):.1f}"
        f", seal {float(item.get('seal_quality_score', 0)):.1f}"
        f", state {item.get('dragon_state', '')}"
        f", gate {item.get('entry_gate', '')}"
        f", tags {tags}"
    )
