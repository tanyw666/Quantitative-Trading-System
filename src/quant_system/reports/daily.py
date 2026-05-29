from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from quant_system.reports.action_advice import render_action_advice_lines
from quant_system.reports.constraint_summary import render_constraint_summary_lines
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
from quant_system.reports.pretrade import render_precheck_summary_lines
from quant_system.reports.strategy_health import render_strategy_health_lines
from quant_system.reports.strategy_rotation import render_strategy_rotation_lines
from quant_system.reports.rotation_history import render_rotation_history_card_lines


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


class DailyReport:
    def render(self, data: DailyReportInput) -> str:
        lines = [
            f"# {data.title}",
            "",
            f"生成日期：{date.today().isoformat()}",
            "",
            "## 0. 今日策略总览",
            "",
            "### 今日优先级总览",
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

        lines.extend(["", "## 1. 市场判断", "", data.market_view, ""])

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

        if data.market_context:
            lines.extend(["## 1.1 真实市场上下文", ""])
            for item in data.market_context.get("summary_lines", []) or ["- 暂无真实市场上下文。"]:
                lines.append(item)
            lines.append("")

        if data.data_health:
            lines.extend(["## 1.2 数据健康", ""])
            lines.extend(render_data_health_lines(data.data_health))
            lines.append("")

        lines.extend(["## 2. 今日候选", ""])
        if data.selected:
            for item in data.selected:
                metrics = []
                if item.get("score") not in (None, ""):
                    metrics.append(f"评分 {float(item['score']):.1f}")
                if item.get("close") not in (None, ""):
                    metrics.append(f"收盘 {item['close']}")
                if item.get("momentum_20") not in (None, ""):
                    metrics.append(f"20日动量 {float(item['momentum_20']):.2%}")
                if item.get("volume_ratio_20") not in (None, ""):
                    metrics.append(f"量比 {float(item['volume_ratio_20']):.2f}")
                if item.get("risk_grade") not in (None, ""):
                    metrics.append(f"风险 {item['risk_grade']}")
                if item.get("atr_stop_price") not in (None, ""):
                    metrics.append(f"ATR止损 {float(item['atr_stop_price']):.2f}")
                suffix = f"（{'，'.join(metrics)}）" if metrics else ""
                lines.append(f"- {item.get('symbol', '')} {item.get('name', '')}：{item.get('reason', '')}{suffix}")
        else:
            lines.append("- 暂无候选，等待数据源和策略输出接入。")

        lines.extend(["", "## 3. 策略参数参考", ""])
        lines.extend(render_experiment_summary_lines(data.experiment_summary))

        lines.extend(["", "## 4. 策略晋升", ""])
        lines.extend(render_promotion_summary_lines(data.promotion_summary))

        lines.extend(["", "## 5. 仓位建议", ""])
        if data.allocation_plan:
            plan = data.allocation_plan
            if plan.get("strategy_adjustment_note"):
                lines.append(f"- 策略约束：{plan.get('strategy_adjustment_note')}")
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

        lines.extend(["", "## 6. 交易前预检预览", ""])
        lines.extend(render_precheck_summary_lines(data.pretrade_checks))

        lines.extend(["", "## 6.1 Gate Discipline", ""])
        lines.extend(render_gate_review_lines(data.gate_review))
        lines.extend(["", "## 6.2 Discipline Advice", ""])
        lines.extend(
            render_discipline_advice_lines(
                gate_review=data.gate_review,
                trade_stats=data.trade_stats,
                allocation_plan=data.allocation_plan,
            )
        )

        lines.extend(["", "## 6.3 Discipline History", ""])
        lines.extend(render_discipline_summary_lines(data.discipline_summary))

        lines.extend(["", "## 6.4 Discipline Adherence", ""])
        lines.extend(render_discipline_adherence_lines(data.discipline_adherence))

        lines.extend(["", "## 7. 明日动作建议", ""])
        lines.extend(
            render_action_advice_lines(
                strategy_health=data.strategy_health,
                constraint_summary=data.constraint_summary,
                allocation_plan=data.allocation_plan,
                market_temperature=data.market_temperature,
            )
        )

        lines.extend(["", "## 8. 风险提示", ""])
        for risk in data.risks:
            lines.append(f"- {risk}")
        lines.append("")
        return "\n".join(lines)


def render_data_health_lines(data_health: dict | None) -> list[str]:
    if not data_health:
        return ["- 暂无数据健康摘要。"]
    issues = list(data_health.get("issues", []))
    lines = [
        f"- 状态：{data_health.get('status', '')}",
        f"- 股票数：{int(data_health.get('symbols', 0))}",
        f"- K线条数：{int(data_health.get('rows', 0))}",
        f"- 覆盖区间：{data_health.get('start_date', '')} 至 {data_health.get('end_date', '')}",
    ]
    focus = [issue for issue in issues if issue.get("status") in {"fail", "warn"}]
    if focus:
        for issue in focus[:3]:
            lines.append(f"- [{_status_label(issue.get('status', ''))}] {_translate_health_message(issue)}")
    else:
        lines.append("- 关键检查：重复、空值、价格合理性、历史长度均通过。")
    return lines


def _status_label(status: str) -> str:
    return {"pass": "通过", "warn": "提示", "fail": "失败", "ok": "正常"}.get(str(status), str(status))


def _translate_health_message(issue: dict) -> str:
    name = str(issue.get("name", ""))
    details = issue.get("details") or {}
    if name == "history_length" and details:
        new_count = int(details.get("new_listing_count", 0) or 0)
        backfill_count = int(details.get("backfill_count", 0) or 0)
        parts: list[str] = []
        if new_count:
            parts.append(f"{new_count} 只近端新股历史较短，不代表缓存损坏")
        if backfill_count:
            parts.append(f"{backfill_count} 只非新股历史不足，建议回填")
        return "；".join(parts) + _sample_suffix(details.get("backfill_samples") or details.get("new_listing_samples"))
    if name == "staleness" and details:
        regular_count = int(details.get("regular_stale_count", 0) or 0)
        special_count = int(details.get("special_stale_count", 0) or 0)
        parts = []
        if regular_count:
            parts.append(f"{regular_count} 只普通股票行情滞后，建议优先回填")
        if special_count:
            parts.append(f"{special_count} 只ST/特殊状态股票滞后，单独观察")
        return "；".join(parts) + _sample_suffix(details.get("regular_stale_samples") or details.get("special_stale_samples"))

    message = str(issue.get("message", ""))
    replacements = {
        "recent/new listings have short history": "只近端新股/新上市股票历史较短",
        "symbols may need backfill": "只股票可能需要回填",
        "regular symbols look stale": "只普通股票行情滞后",
        "ST/special-status symbols stale separately": "只ST/特殊状态股票行情滞后，单独观察",
        "As of": "基准日",
        "oldest cached date reaches": "最早缓存日期",
    }
    for source, target in replacements.items():
        message = message.replace(source, target)
    if name == "history_length" and "近端新股" in message:
        return "短历史主要来自新股，不代表缓存损坏：" + message
    if name == "staleness" and "普通股票行情滞后" in message:
        return "需优先回填普通股票滞后项，ST/特殊状态另行观察：" + message
    return message


def _sample_suffix(samples: object) -> str:
    if not isinstance(samples, list) or not samples:
        return ""
    labels = []
    for item in samples[:5]:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip()
        name = str(item.get("name", "")).strip()
        latest = str(item.get("last_date", "")).strip()
        label = f"{symbol} {name}".strip()
        labels.append(f"{label}({latest})" if latest else label)
    return f"。样本：{', '.join(labels)}" if labels else ""
