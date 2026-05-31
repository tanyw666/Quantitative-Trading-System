from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any


@dataclass(frozen=True)
class TradingDayPhase:
    phase: str
    status: str
    title: str
    due: str
    checklist: list[str]
    missing: list[str]
    next_step: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "title": self.title,
            "due": self.due,
            "checklist": list(self.checklist),
            "missing": list(self.missing),
            "next_step": self.next_step,
        }


def build_trading_day_timeline(
    *,
    now: datetime | None = None,
    final_battle_plan: dict[str, Any] | None = None,
    execution_confirmations: list[dict[str, Any]] | None = None,
    trade_records: list[dict[str, Any]] | None = None,
    execution_audit: dict[str, Any] | None = None,
    lifecycle_snapshot: dict[str, Any] | None = None,
    gate_review: dict[str, Any] | None = None,
    approval_cooldown: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = now or datetime.now()
    final_battle_plan = final_battle_plan or {}
    execution_confirmations = list(execution_confirmations or [])
    trade_records = list(trade_records or [])
    execution_audit = execution_audit or {}
    lifecycle_snapshot = lifecycle_snapshot or {}
    gate_review = gate_review or {}
    approval_cooldown = approval_cooldown or {}

    phases = [
        _premarket_phase(now, final_battle_plan, approval_cooldown),
        _intraday_phase(now, final_battle_plan, execution_confirmations, approval_cooldown),
        _post_trade_phase(now, execution_confirmations, trade_records, execution_audit, gate_review),
        _approval_phase(now, approval_cooldown),
        _lifecycle_phase(now, lifecycle_snapshot, execution_audit, gate_review),
    ]
    overall_status = _rollup_status([phase.status for phase in phases])
    return {
        "generated_at": now.isoformat(),
        "status": overall_status,
        "phases": [phase.to_dict() for phase in phases],
        "action_items": _action_items(phases),
    }


def render_trading_day_timeline_markdown(timeline: dict[str, Any] | None) -> str:
    timeline = timeline or {}
    if not timeline:
        return "# 交易日时间线\n\n- 暂无阶段提醒数据。\n"
    lines = [
        "# 交易日时间线",
        "",
        f"- 状态：{timeline.get('status', '')}",
        f"- 生成时间：{timeline.get('generated_at', '')}",
    ]
    phases = list(timeline.get("phases") or [])
    for phase in phases:
        lines.extend(["", f"## {phase.get('title', '')}", ""])
        lines.append(f"- 状态：{phase.get('status', '')}")
        lines.append(f"- 截止：{phase.get('due', '')}")
        lines.append(f"- 下一步：{phase.get('next_step', '')}")
        missing = list(phase.get("missing") or [])
        if missing:
            lines.append("- 缺口：")
            lines.extend(f"  - {item}" for item in missing)
        checklist = list(phase.get("checklist") or [])
        if checklist:
            lines.append("- 清单：")
            lines.extend(f"  - {item}" for item in checklist)
    action_items = list(timeline.get("action_items") or [])
    if action_items:
        lines.extend(["", "## 汇总提醒", ""])
        lines.extend(f"- {item}" for item in action_items)
    return "\n".join(lines)


def _premarket_phase(now: datetime, final_battle_plan: dict[str, Any], approval_cooldown: dict[str, Any]) -> TradingDayPhase:
    status = "pass"
    if not final_battle_plan:
        status = "warn"
    elif str(final_battle_plan.get("status", "") or "") == "block":
        status = "block"
    elif str(final_battle_plan.get("status", "") or "") == "warn":
        status = "warn"
    if str(approval_cooldown.get("status", "") or "") == "block":
        status = "block"
    checklist = [
        "确认数据健康、市场温度、候选池和最终作战单已经生成。",
        "检查审批冷静期是否产生策略暂停或仓位下调约束。",
    ]
    missing = []
    if not final_battle_plan:
        missing.append("最终作战单尚未生成。")
    elif not final_battle_plan.get("buy_candidates") and not final_battle_plan.get("blocked_candidates"):
        missing.append("最终作战单没有展开候选列表；需要确认筛选条件是否过严。")
    if str(approval_cooldown.get("status", "") or "") == "block":
        missing.append("审批冷静期在开盘前阻断相关策略。")
    return TradingDayPhase(
        phase="premarket",
        status=status,
        title="盘前准备阶段",
        due="开盘前",
        checklist=checklist,
        missing=missing,
        next_step="先运行 trading-day 工作流并复核最终作战单，再考虑任何订单。",
    )


def _intraday_phase(
    now: datetime,
    final_battle_plan: dict[str, Any],
    execution_confirmations: list[dict[str, Any]],
    approval_cooldown: dict[str, Any],
) -> TradingDayPhase:
    market_open = time(9, 30)
    market_close = time(15, 0)
    status = "pass"
    if str(approval_cooldown.get("status", "") or "") == "block":
        status = "block"
    elif market_open <= now.time() <= market_close and not execution_confirmations and list(final_battle_plan.get("buy_candidates") or []):
        status = "warn"
    checklist = [
        "每一笔真实 BUY 下单前先运行 portfolio confirm。",
        "每一笔 BUY 成交都要绑定执行确认和最终订单审批。",
    ]
    missing = []
    if list(final_battle_plan.get("buy_candidates") or []) and not execution_confirmations:
        missing.append("存在可执行候选，但尚未生成执行确认。")
    if str(approval_cooldown.get("status", "") or "") == "block":
        missing.append("审批冷静期阻断盘中新 BUY 执行。")
    return TradingDayPhase(
        phase="intraday",
        status=status,
        title="盘中执行阶段",
        due="交易时段",
        checklist=checklist,
        missing=missing,
        next_step="准备下单时运行 portfolio confirm；已经成交则用 review trade-add 回写。",
    )


def _post_trade_phase(
    now: datetime,
    execution_confirmations: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    execution_audit: dict[str, Any],
    gate_review: dict[str, Any],
) -> TradingDayPhase:
    status = "pass"
    if int(execution_audit.get("missing_trade_writeback_count", 0) or 0) > 0:
        status = "warn"
    if int(execution_audit.get("block_count", 0) or 0) > 0:
        status = "block"
    if int(gate_review.get("violation_count", 0) or 0) > 0:
        status = _escalate(status, "warn")
    checklist = [
        "确认每一笔成交都已用 review trade-add 回写。",
        "确认交易记录与执行确认的数量、价格、状态一致。",
    ]
    missing = []
    if execution_confirmations and not trade_records:
        missing.append("已有执行确认，但未发现成交回写。")
    if int(execution_audit.get("missing_confirmation_trade_count", 0) or 0) > 0:
        missing.append("存在缺少执行确认的 BUY 交易。")
    return TradingDayPhase(
        phase="post_trade",
        status=status,
        title="成交回写阶段",
        due="成交后立即",
        checklist=checklist,
        missing=missing,
        next_step="收盘后运行 review execution-audit 和 report cockpit。",
    )


def _approval_phase(now: datetime, approval_cooldown: dict[str, Any]) -> TradingDayPhase:
    status = str(approval_cooldown.get("status", "") or "pass")
    constraints = list(approval_cooldown.get("constraints") or [])
    missing = []
    if status in {"warn", "block"}:
        missing.append("审批纪律存在生效中的冷静期约束。")
    checklist = [
        "相关策略重新放行前，先复核审批审计违规。",
        "每一笔成交都必须显式绑定最终订单审批。",
    ]
    return TradingDayPhase(
        phase="approval_discipline",
        status=status,
        title="审批纪律阶段",
        due="下一次 BUY 前",
        checklist=checklist,
        missing=missing,
        next_step=f"复核 {len(constraints)} 条审批冷静期约束，只有干净审计后才清除。",
    )


def _lifecycle_phase(
    now: datetime,
    lifecycle_snapshot: dict[str, Any],
    execution_audit: dict[str, Any],
    gate_review: dict[str, Any],
) -> TradingDayPhase:
    status = str(lifecycle_snapshot.get("status", "") or "pass")
    if int(execution_audit.get("block_count", 0) or 0) > 0:
        status = _escalate(status, "block")
    elif int(execution_audit.get("warn_count", 0) or 0) > 0:
        status = _escalate(status, "warn")
    if int(gate_review.get("violation_count", 0) or 0) > 0:
        status = _escalate(status, "warn")
    checklist = [
        "收盘后刷新持仓生命周期快照。",
        "确认交易计划、持仓动作、退出计划、执行审计和审批审计都闭环。",
    ]
    missing = []
    if not lifecycle_snapshot:
        missing.append("持仓生命周期快照尚未生成。")
    return TradingDayPhase(
        phase="lifecycle",
        status=status,
        title="收盘生命周期阶段",
        due="收盘后",
        checklist=checklist,
        missing=missing,
        next_step="收盘后运行 workflow trading-day 或 review lifecycle-history。",
    )


def _action_items(phases: list[TradingDayPhase]) -> list[str]:
    items: list[str] = []
    for phase in phases:
        if phase.status in {"warn", "block"}:
            items.append(f"{phase.title}: {phase.next_step}")
        for missing in phase.missing:
            items.append(missing)
    if not items:
        items.append("交易日提醒全部干净；继续按阶段顺序执行。")
    return items


def _rollup_status(statuses: list[str]) -> str:
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"


def _escalate(current: str, target: str) -> str:
    rank = {"pass": 0, "warn": 1, "block": 2}
    return target if rank.get(target, 0) > rank.get(current, 0) else current
