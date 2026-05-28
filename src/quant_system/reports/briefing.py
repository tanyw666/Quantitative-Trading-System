from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quant_system.reports.experiment_summary import render_experiment_summary_lines


@dataclass(frozen=True)
class BriefingInput:
    title: str
    market_temperature: dict
    candidates: list[dict]
    allocation_plan: dict
    position_book: dict
    holding_risk: dict
    sectors: list[dict] | None = None
    experiment_summary: dict | None = None


class BriefingReport:
    def render(self, data: BriefingInput) -> str:
        lines = [
            f"# {data.title}",
            "",
            f"生成日期：{date.today().isoformat()}",
            "",
            "## 1. 市场温度",
            "",
        ]
        temp = data.market_temperature
        lines.extend(
            [
                f"- 温度：{float(temp.get('score', 0)):.1f}/100",
                f"- 状态：{temp.get('regime', '')}",
                f"- 建议：{temp.get('stance', '')}",
                f"- 上涨占比：{float(temp.get('advance_ratio', 0)):.1%}",
                f"- 站上MA20：{float(temp.get('above_ma20_ratio', 0)):.1%}",
                "",
                "## 2. 今日候选",
                "",
            ]
        )

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

        plan = data.allocation_plan
        lines.extend(
            [
                "",
                "## 5. 仓位计划",
                "",
                f"- 目标总仓位：{float(plan.get('target_exposure_pct', 0)):.1%}",
                f"- 已分配仓位：{float(plan.get('allocated_pct', 0)):.1%}",
            ]
        )
        for item in plan.get("items", []):
            lines.append(
                f"- {item.get('symbol', '')} {item.get('name', '')}："
                f"{float(item.get('target_pct', 0)):.1%}，"
                f"约 {float(item.get('target_value', 0)):.2f}"
            )

        book = data.position_book
        lines.extend(
            [
                "",
                "## 6. 当前持仓",
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
        lines.extend(["", "## 7. 风险检查", "", f"- 总状态：{risk.get('status', '')}"])
        for check in risk.get("checks", []):
            lines.append(f"- [{check.get('status', '')}] {check.get('message', '')}")

        lines.extend(["", "## 8. 今日动作", ""])
        lines.extend(action_notes(temp, data.candidates, risk))
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
        notes.append("- 只从高评分候选中选择，买入前必须运行 precheck。")
    else:
        notes.append("- 无候选，不做强行交易。")
    notes.append("- 所有实际交易必须写入 trade-add，盘后复盘执行偏差。")
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
