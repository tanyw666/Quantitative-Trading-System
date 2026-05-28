from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quant_system.reports.experiment_summary import render_experiment_summary_lines
from quant_system.reports.promotion_summary import render_promotion_summary_lines


@dataclass(frozen=True)
class DailyReportInput:
    title: str
    market_view: str
    selected: list[dict]
    risks: list[str]
    market_temperature: dict | None = None
    allocation_plan: dict | None = None
    experiment_summary: dict | None = None
    promotion_summary: dict | None = None


class DailyReport:
    def render(self, data: DailyReportInput) -> str:
        lines = [
            f"# {data.title}",
            "",
            f"生成日期：{date.today().isoformat()}",
            "",
            "## 1. 市场判断",
            "",
            data.market_view,
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

        lines.extend(["## 2. 今日候选", ""])
        if data.selected:
            for item in data.selected:
                symbol = item.get("symbol", "")
                name = item.get("name", "")
                reason = item.get("reason", "")
                close = item.get("close", "")
                momentum = item.get("momentum_20", "")
                volume_ratio = item.get("volume_ratio_20", "")
                score = item.get("score", "")
                risk_grade = item.get("risk_grade", "")
                stop_price = item.get("atr_stop_price", "")
                metrics = []
                if score != "":
                    metrics.append(f"评分 {float(score):.1f}")
                if close != "":
                    metrics.append(f"收盘 {close}")
                if momentum != "":
                    metrics.append(f"20日动量 {float(momentum):.2%}")
                if volume_ratio != "":
                    metrics.append(f"量比 {float(volume_ratio):.2f}")
                if risk_grade != "":
                    metrics.append(f"风险 {risk_grade}")
                if stop_price != "":
                    metrics.append(f"ATR止损 {float(stop_price):.2f}")
                suffix = f"（{'，'.join(metrics)}）" if metrics else ""
                lines.append(f"- {symbol} {name}：{reason}{suffix}")
        else:
            lines.append("- 暂无候选，等待数据源和策略输出接入。")

        lines.extend(["", "## 3. 策略参数参考", ""])
        lines.extend(render_experiment_summary_lines(data.experiment_summary))

        lines.extend(["", "## 4. 策略晋升", ""])
        lines.extend(render_promotion_summary_lines(data.promotion_summary))

        lines.extend(["", "## 5. 仓位建议", ""])
        if data.allocation_plan:
            plan = data.allocation_plan
            lines.append(
                f"- 目标总仓位：{float(plan.get('target_exposure_pct', 0)):.1%}"
                f"（约 {float(plan.get('target_exposure_value', 0)):.2f}）"
            )
            lines.append(
                f"- 已分配仓位：{float(plan.get('allocated_pct', 0)):.1%}"
                f"（约 {float(plan.get('allocated_value', 0)):.2f}）"
            )
            for item in plan.get("items", []):
                stop = item.get("stop_price")
                stop_text = f"，参考止损 {float(stop):.2f}" if stop is not None else ""
                lines.append(
                    f"- {item.get('symbol', '')} {item.get('name', '')}："
                    f"{float(item.get('target_pct', 0)):.1%}"
                    f"（约 {float(item.get('target_value', 0)):.2f}，风险 {item.get('risk_grade', '')}{stop_text}）"
                )
        else:
            lines.append("- 暂无仓位建议。")

        lines.extend(["", "## 6. 风险提示", ""])
        for risk in data.risks:
            lines.append(f"- {risk}")
        lines.append("")
        return "\n".join(lines)
