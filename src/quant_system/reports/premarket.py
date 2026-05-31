from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quant_system.reports.action_advice import render_action_advice_lines
from quant_system.reports.constraint_summary import render_constraint_summary_lines
from quant_system.reports.discipline_adherence import render_discipline_adherence_lines
from quant_system.reports.daily import render_data_health_lines
from quant_system.reports.discipline_advice import render_discipline_advice_lines
from quant_system.reports.discipline_summary import render_discipline_summary_lines
from quant_system.reports.gate_review import render_gate_review_lines
from quant_system.portfolio.position_actions import render_position_action_plan_lines
from quant_system.portfolio.action_execution import render_action_execution_lines
from quant_system.portfolio.exit_plan import render_exit_execution_lines, render_exit_plan_lines, render_lot_exit_execution_lines
from quant_system.portfolio.lots import render_lot_book_lines
from quant_system.reports.position_lifecycle import render_position_lifecycle_lines
from quant_system.reports.pretrade import render_precheck_summary_lines
from quant_system.reports.rotation_history import render_rotation_history_card_lines
from quant_system.reports.strategy_health import render_strategy_health_lines
from quant_system.reports.strategy_rotation import render_strategy_rotation_lines
from quant_system.reports.strategy_portfolio import render_strategy_portfolio_lines
from quant_system.reports.final_battle_plan import render_final_battle_plan_lines


@dataclass(frozen=True)
class PremarketReportInput:
    title: str
    market_temperature: dict
    market_context: dict | None
    data_health: dict | None
    candidates: list[dict]
    allocation_plan: dict | None
    pretrade_checks: list[dict] | None
    position_book: dict | None
    holding_risk: dict | None
    lot_book: dict | None = None
    holding_action_plan: dict | None = None
    exit_plan: dict | None = None
    strategy_health: list[dict] | None = None
    constraint_summary: dict | None = None
    strategy_rotation: list[dict] | None = None
    strategy_portfolio: dict | None = None
    rotation_history: dict | None = None
    gate_review: dict | None = None
    trade_stats: dict | None = None
    action_execution_summary: dict | None = None
    exit_execution_summary: dict | None = None
    lot_exit_execution_summary: dict | None = None
    lifecycle_snapshot: dict | None = None
    discipline_summary: dict | None = None
    discipline_adherence: dict | None = None
    final_battle_plan: dict | None = None


class PremarketReport:
    def render(self, data: PremarketReportInput) -> str:
        lines = [
            f"# {data.title}",
            "",
            f"生成日期：{date.today().isoformat()}",
            "",
            "## 0. 开盘前结论",
            "",
            f"- 结论：{premarket_decision(data.market_temperature, data.pretrade_checks, data.holding_risk, data.allocation_plan)}",
            f"- 市场状态：{data.market_temperature.get('regime', '')}，{data.market_temperature.get('stance', '')}",
            f"- 持仓风险：{(data.holding_risk or {}).get('status', 'pass')}",
        ]
        lines.extend(
            render_action_advice_lines(
                strategy_health=data.strategy_health,
                constraint_summary=data.constraint_summary,
                allocation_plan=data.allocation_plan,
                market_temperature=data.market_temperature,
                holding_action_plan=data.holding_action_plan,
                exit_plan=data.exit_plan,
            )
        )

        lines.extend(["", "### 最终作战单", ""])
        lines.extend(render_final_battle_plan_lines(data.final_battle_plan))

        lines.extend(["", "## 1. 数据与市场", ""])
        if data.data_health:
            lines.extend(render_data_health_lines(data.data_health))
        else:
            lines.append("- 暂无数据健康摘要。")
        if data.market_context:
            lines.append("")
            for item in data.market_context.get("summary_lines", []) or ["- 暂无真实市场上下文。"]:
                lines.append(item)

        lines.extend(["", "## 2. 策略与仓位", ""])
        lines.extend(render_strategy_health_lines(data.strategy_health))
        lines.extend(["", "### 策略约束", ""])
        lines.extend(render_constraint_summary_lines(data.constraint_summary))
        lines.extend(["", "### 策略轮换", ""])
        lines.extend(render_strategy_rotation_lines(data.strategy_rotation))
        lines.extend(["", "### 策略组合管理器", ""])
        lines.extend(render_strategy_portfolio_lines(data.strategy_portfolio))
        lines.extend(["", "### 轮换历史", ""])
        lines.extend(render_rotation_history_card_lines(data.rotation_history))
        lines.extend(["", "### 仓位计划", ""])
        lines.extend(render_allocation_lines(data.allocation_plan))

        lines.extend(["", "## 3. 候选与预检", ""])
        if data.candidates:
            for item in data.candidates[:5]:
                lines.append(
                    f"- {item.get('symbol', '')} {item.get('name', '')}："
                    f"评分 {float(item.get('score', 0)):.1f}，"
                    f"风险 {item.get('risk_grade', '')}，"
                    f"收盘 {item.get('close', '')}"
                )
        else:
            lines.append("- 暂无候选。")
        lines.extend(["", "### 交易前预检", ""])
        lines.extend(render_precheck_summary_lines(data.pretrade_checks))
        lines.extend(["", "### Gate Discipline", ""])
        lines.extend(render_gate_review_lines(data.gate_review))
        lines.extend(["", "### Discipline Advice", ""])
        lines.extend(
            render_discipline_advice_lines(
                gate_review=data.gate_review,
                trade_stats=data.trade_stats,
                holding_risk=data.holding_risk,
                allocation_plan=data.allocation_plan,
            )
        )

        lines.extend(["", "### Discipline History", ""])
        lines.extend(render_discipline_summary_lines(data.discipline_summary))

        lines.extend(["", "### Discipline Adherence", ""])
        lines.extend(render_discipline_adherence_lines(data.discipline_adherence))

        lines.extend(["", "## 4. 持仓风险", ""])
        lines.extend(render_position_lines(data.position_book))
        lines.extend(["", "### Lot Lifecycle", ""])
        lines.extend(render_lot_book_lines(data.lot_book, limit=5))
        for check in (data.holding_risk or {}).get("checks", []) or []:
            lines.append(f"- [{check.get('status', '')}] {check.get('message', '')}")
        lines.extend(["", "### 持仓动作计划", ""])
        lines.extend(render_position_action_plan_lines(data.holding_action_plan))
        lines.extend(["", "### Exit Plan", ""])
        lines.extend(render_exit_plan_lines(data.exit_plan))
        lines.extend(["", "### 持仓动作执行审计", ""])
        lines.extend(render_action_execution_lines(data.action_execution_summary))
        lines.extend(["", "### Exit Execution Audit", ""])
        lines.extend(render_exit_execution_lines(data.exit_execution_summary))
        lines.extend(["", "### Lot Exit Execution Audit", ""])
        lines.extend(render_lot_exit_execution_lines(data.lot_exit_execution_summary))
        lines.extend(["", "### Position Lifecycle", ""])
        lines.extend(render_position_lifecycle_lines(data.lifecycle_snapshot))
        lines.append("")
        return "\n".join(lines)


def premarket_decision(
    market_temperature: dict | None,
    pretrade_checks: list[dict] | None,
    holding_risk: dict | None,
    allocation_plan: dict | None = None,
) -> str:
    risk_status = str((holding_risk or {}).get("status", "pass") or "pass")
    regime = str((market_temperature or {}).get("regime", "") or "")
    statuses = {str(item.get("status", "") or "") for item in (pretrade_checks or [])}
    strategy_action = str((allocation_plan or {}).get("strategy_action", "") or "")
    strategy_alert = str((allocation_plan or {}).get("strategy_alert_level", "pass") or "pass")
    if risk_status == "block" or "block" in statuses or regime in {"frozen", "empty"} or strategy_action == "pause" or strategy_alert == "block":
        return "禁止新开仓，先处理阻断项。"
    if risk_status == "warn" or "warn" in statuses or regime == "cold" or strategy_action == "reduce" or strategy_alert == "warn":
        return "只允许计划内确认单，禁止追高加仓。"
    return "可按计划执行，但所有买入必须先完成正式 precheck。"


def render_allocation_lines(plan: dict | None) -> list[str]:
    if not plan:
        return ["- 暂无仓位计划。"]
    lines = [
        f"- 目标总仓位：{float(plan.get('target_exposure_pct', 0)):.1%}",
        f"- 已分配仓位：{float(plan.get('allocated_pct', 0)):.1%}",
    ]
    if plan.get("strategy_adjustment_note"):
        lines.append(f"- 策略约束：{plan.get('strategy_adjustment_note')}")
    for item in plan.get("items", []) or []:
        stop = item.get("stop_price")
        stop_text = f"，止损 {float(stop):.2f}" if stop is not None else ""
        lines.append(
            f"- {item.get('symbol', '')} {item.get('name', '')}："
            f"{float(item.get('target_pct', 0)):.1%}，"
            f"资金 {float(item.get('target_value', 0)):.2f}{stop_text}"
        )
    return lines


def render_position_lines(book: dict | None) -> list[str]:
    if not book:
        return ["- 暂无持仓视图。"]
    lines = [
        f"- 总市值：{float(book.get('total_market_value', 0)):.2f}",
        f"- 总暴露：{float(book.get('total_exposure_pct', 0)):.1%}",
        f"- 总浮盈亏：{float(book.get('total_unrealized_pnl', 0)):.2f}",
    ]
    positions = book.get("positions", []) or []
    if not positions:
        lines.append("- 当前无持仓。")
    for item in positions:
        lines.append(
            f"- {item.get('symbol', '')} {item.get('name', '')}："
            f"{int(item.get('quantity', 0))} 股，成本 {float(item.get('avg_cost', 0)):.2f}"
        )
    return lines
