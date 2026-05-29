from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from quant_system.risk.pretrade import PreTradeResult
from quant_system.risk.sizing import AllocationPlan
from quant_system.storage.jsonl import append_jsonl, read_jsonl


@dataclass(frozen=True)
class TradePlanItem:
    symbol: str
    name: str
    planned_pct: float
    planned_value: float
    entry_price: float
    stop_price: float | None
    target_price: float | None
    risk_grade: str
    reason: str
    pretrade_status: str
    gate_status: str
    gate_reason: str
    discipline_exception: bool = False
    exception_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TradePlan:
    created_at: str
    trade_date: str
    symbol: str
    name: str
    strategy: str
    market_regime: str
    stance: str
    status: str
    gate_status: str
    gate_reason: str
    planned_pct: float
    planned_value: float
    allowed_pct: float
    allowed_value: float
    entry_price: float
    stop_price: float | None
    target_price: float | None
    stop_loss_pct: float | None
    reward_risk: float | None
    max_loss_value: float | None
    expected_reward_value: float | None
    risk_grade: str
    candidate_snapshot: dict[str, Any] | None = None
    strategy_constraint: dict | None = None
    allocation_plan: dict | None = None
    pretrade_checks: list[dict] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    items: list[TradePlanItem] = field(default_factory=list)
    discipline_exception: bool = False
    exception_reason: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["items"] = [item.to_dict() for item in self.items]
        return data


@dataclass(frozen=True)
class TradePlanBatch:
    created_at: str
    trade_date: str
    strategy: str
    market_regime: str
    stance: str
    status: str
    gate_status: str
    total_candidates: int
    total_plans: int
    total_planned_value: float
    total_allowed_value: float
    plans: list[TradePlan] = field(default_factory=list)
    candidate_snapshot: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["plans"] = [plan.to_dict() for plan in self.plans]
        return data


def build_trade_plan(
    *,
    symbol: str,
    trade_date: str | None,
    pretrade_result: PreTradeResult,
    allocation_plan: AllocationPlan,
    discipline_exception: bool = False,
    exception_reason: str = "",
) -> TradePlan:
    candidate = pretrade_result.candidate_snapshot or {}
    item = _build_item(
        pretrade_result=pretrade_result,
        allocation_plan=allocation_plan,
        discipline_exception=discipline_exception,
        exception_reason=exception_reason,
    )
    return TradePlan(
        created_at=datetime.now(timezone.utc).isoformat(),
        trade_date=trade_date or date.today().isoformat(),
        symbol=str(symbol).zfill(6),
        name=str(candidate.get("name", "") or ""),
        strategy=str((allocation_plan.strategy_constraint or {}).get("strategy", "") or ""),
        market_regime=str(allocation_plan.regime),
        stance=str(allocation_plan.stance),
        status=str(pretrade_result.status),
        gate_status=_gate_status(pretrade_result.status),
        gate_reason=_gate_reason(pretrade_result),
        planned_pct=float(pretrade_result.planned_pct),
        planned_value=float(pretrade_result.planned_value),
        allowed_pct=float(pretrade_result.allowed_pct),
        allowed_value=float(pretrade_result.allowed_value),
        entry_price=float(pretrade_result.entry_price),
        stop_price=pretrade_result.stop_price,
        target_price=pretrade_result.target_price,
        stop_loss_pct=pretrade_result.stop_loss_pct,
        reward_risk=pretrade_result.reward_risk,
        max_loss_value=pretrade_result.max_loss_value,
        expected_reward_value=pretrade_result.expected_reward_value,
        risk_grade=str((candidate or {}).get("risk_grade", "") or ""),
        candidate_snapshot=candidate or None,
        strategy_constraint=allocation_plan.strategy_constraint,
        allocation_plan=allocation_plan.to_dict(),
        pretrade_checks=[check.to_dict() for check in pretrade_result.checks],
        action_items=list(pretrade_result.action_items),
        items=[item],
        discipline_exception=bool(discipline_exception),
        exception_reason=str(exception_reason or "").strip(),
    )


def build_trade_plan_batch(
    *,
    candidates,
    market_temperature: dict,
    cash: float,
    max_positions: int,
    strategy_health: dict | None = None,
    trade_date: str | None = None,
    discipline_exception: bool = False,
    exception_reason: str = "",
) -> TradePlanBatch:
    from quant_system.risk.pretrade import run_pretrade_check
    from quant_system.risk.sizing import build_allocation_plan

    allocation_plan = build_allocation_plan(
        candidates,
        market_temperature,
        cash=cash,
        max_positions=max_positions,
        strategy_health=strategy_health,
    )
    candidate_snapshot = candidates.to_dict(orient="records") if hasattr(candidates, "to_dict") else list(candidates or [])
    plans: list[TradePlan] = []
    for item in allocation_plan.items[:max_positions]:
        symbol = str(item.symbol).zfill(6)
        entry_price = _candidate_entry_price(candidate_snapshot, symbol)
        if entry_price is None:
            continue
        stop_price = item.stop_price
        target_price = _preview_target_price(entry_price, stop_price)
        result = run_pretrade_check(
            candidates,
            market_temperature,
            symbol=symbol,
            entry_price=entry_price,
            planned_pct=float(item.target_pct),
            cash=cash,
            stop_price=stop_price,
            target_price=target_price,
            max_positions=max_positions,
            strategy_health=strategy_health,
        )
        plans.append(
            build_trade_plan(
                symbol=symbol,
                trade_date=trade_date,
                pretrade_result=result,
                allocation_plan=allocation_plan,
                discipline_exception=discipline_exception,
                exception_reason=exception_reason,
            )
        )
    return TradePlanBatch(
        created_at=datetime.now(timezone.utc).isoformat(),
        trade_date=trade_date or date.today().isoformat(),
        strategy=str((allocation_plan.strategy_constraint or {}).get("strategy", "") or ""),
        market_regime=str(allocation_plan.regime),
        stance=str(allocation_plan.stance),
        status="block" if any(plan.status == "block" for plan in plans) else "pass",
        gate_status="warn" if any(plan.gate_status in {"warn", "block"} for plan in plans) else "pass",
        total_candidates=len(candidate_snapshot),
        total_plans=len(plans),
        total_planned_value=round(sum(plan.planned_value for plan in plans), 2),
        total_allowed_value=round(sum(plan.allowed_value for plan in plans), 2),
        plans=plans,
        candidate_snapshot=candidate_snapshot,
    )


def render_trade_plan_markdown(plan: TradePlan) -> str:
    lines = [
        f"# 交易计划 {plan.symbol}",
        "",
        f"- 日期：{plan.trade_date}",
        f"- 标的：{plan.symbol} {plan.name}".strip(),
        f"- 策略：{plan.strategy}",
        f"- 市场：{plan.market_regime} / {plan.stance}",
        f"- 状态：{plan.status}",
        f"- 门禁：{plan.gate_status}",
        f"- 计划仓位：{plan.planned_pct:.1%}（{plan.planned_value:.2f}）",
        f"- 可用仓位：{plan.allowed_pct:.1%}（{plan.allowed_value:.2f}）",
        f"- 买入价：{plan.entry_price:.2f}",
    ]
    if plan.stop_price is not None:
        lines.append(f"- 止损价：{plan.stop_price:.2f}")
    if plan.target_price is not None:
        lines.append(f"- 目标价：{plan.target_price:.2f}")
    if plan.reward_risk is not None:
        lines.append(f"- 盈亏比：{plan.reward_risk:.2f}")
    if plan.discipline_exception:
        lines.append(f"- 纪律例外：是（{plan.exception_reason or '未填写理由'}）")
    lines.extend(["", "## 检查项", ""])
    for check in plan.pretrade_checks:
        lines.append(f"- [{check.get('status', '')}] {check.get('name', '')}: {check.get('message', '')}")
    lines.extend(["", "## 动作清单", ""])
    for item in plan.action_items:
        lines.append(f"- {item}")
    return "\n".join(lines)


def render_trade_plan_batch_markdown(batch: TradePlanBatch) -> str:
    lines = [
        f"# 交易计划批次 {batch.trade_date}",
        "",
        f"- Strategy: {batch.strategy}",
        f"- Market: {batch.market_regime} / {batch.stance}",
        f"- Status: {batch.status}",
        f"- Gate: {batch.gate_status}",
        f"- Candidates: {batch.total_candidates}",
        f"- Plans: {batch.total_plans}",
        f"- Planned Value: {batch.total_planned_value:.2f}",
        f"- Allowed Value: {batch.total_allowed_value:.2f}",
        "",
        "## Plans",
        "",
    ]
    for plan in batch.plans:
        lines.append(f"- {plan.symbol} {plan.name} {plan.gate_status} {plan.planned_pct:.1%} {plan.entry_price:.2f}")
    return "\n".join(lines)


def _build_item(
    *,
    pretrade_result: PreTradeResult,
    allocation_plan: AllocationPlan,
    discipline_exception: bool,
    exception_reason: str,
) -> TradePlanItem:
    candidate = pretrade_result.candidate_snapshot or {}
    plan_item = allocation_plan.items[0] if allocation_plan.items else None
    planned_pct = float(pretrade_result.planned_pct)
    planned_value = float(pretrade_result.planned_value)
    if plan_item is not None:
        planned_pct = float(plan_item.target_pct)
        planned_value = float(plan_item.target_value)
    return TradePlanItem(
        symbol=str(pretrade_result.symbol),
        name=str(candidate.get("name", "") or ""),
        planned_pct=planned_pct,
        planned_value=planned_value,
        entry_price=float(pretrade_result.entry_price),
        stop_price=pretrade_result.stop_price,
        target_price=pretrade_result.target_price,
        risk_grade=str(candidate.get("risk_grade", "") or ""),
        reason=str(candidate.get("reason", "") or ""),
        pretrade_status=str(pretrade_result.status),
        gate_status=_gate_status(pretrade_result.status),
        gate_reason=_gate_reason(pretrade_result),
        discipline_exception=bool(discipline_exception),
        exception_reason=str(exception_reason or "").strip(),
    )


def _gate_status(status: str) -> str:
    status = str(status or "").lower()
    if status == "block":
        return "block"
    if status == "warn":
        return "warn"
    return "pass"


def _gate_reason(pretrade_result: PreTradeResult) -> str:
    messages = [check.message for check in pretrade_result.checks if check.status in {"warn", "block"}]
    return "；".join(messages[:3])


def _candidate_entry_price(candidates: list[dict[str, Any]], symbol: str) -> float | None:
    for item in candidates:
        if str(item.get("symbol", "")).strip().zfill(6) != symbol:
            continue
        value = item.get("close")
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _preview_target_price(entry_price: float, stop_price: float | None) -> float:
    if stop_price is not None and stop_price < entry_price:
        return round(entry_price + (entry_price - stop_price) * 2.0, 2)
    return round(entry_price * 1.08, 2)


def read_trade_plan_records(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def summarize_trade_plan_records(records: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    visible_limit = max(int(limit), 0)
    visible = records[-visible_limit:] if visible_limit else records
    status_counts: dict[str, int] = {}
    gate_counts: dict[str, int] = {}
    exception_count = 0
    planned_value = 0.0
    allowed_value = 0.0
    for record in records:
        status = str(record.get("status", "") or "")
        gate = str(record.get("gate_status", "") or "")
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1
        if gate:
            gate_counts[gate] = gate_counts.get(gate, 0) + 1
        if record.get("discipline_exception"):
            exception_count += 1
        planned_value += float(record.get("planned_value", 0) or 0)
        allowed_value += float(record.get("allowed_value", 0) or 0)
    return {
        "total": len(records),
        "pass_count": status_counts.get("pass", 0),
        "warn_count": status_counts.get("warn", 0),
        "block_count": status_counts.get("block", 0),
        "gate_counts": gate_counts,
        "exception_count": exception_count,
        "planned_value": round(planned_value, 2),
        "allowed_value": round(allowed_value, 2),
        "records": visible,
    }


def render_trade_plan_summary_markdown(summary: dict[str, Any] | None) -> str:
    summary = summary or {}
    lines = [
        "# 交易计划汇总",
        "",
        f"- Records: {int(summary.get('total', 0) or 0)}",
        f"- Pass/warn/block: {int(summary.get('pass_count', 0) or 0)} / {int(summary.get('warn_count', 0) or 0)} / {int(summary.get('block_count', 0) or 0)}",
        f"- Exceptions: {int(summary.get('exception_count', 0) or 0)}",
        f"- Planned Value: {float(summary.get('planned_value', 0) or 0):.2f}",
        f"- Allowed Value: {float(summary.get('allowed_value', 0) or 0):.2f}",
    ]
    records = list(summary.get("records", []) or [])
    if records:
        lines.extend(["", "| Date | Symbol | Status | Gate | Planned | Entry | Exception |", "| --- | --- | --- | --- | ---: | ---: | --- |"])
        for record in records:
            lines.append(
                f"| {record.get('trade_date', record.get('date', ''))} | "
                f"{record.get('symbol', '')} | "
                f"{record.get('status', '')} | "
                f"{record.get('gate_status', '')} | "
                f"{float(record.get('planned_pct', 0) or 0):.1%} | "
                f"{float(record.get('entry_price', record.get('planned_price', 0)) or 0):.2f} | "
                f"{record.get('exception_reason', '')} |"
            )
    return "\n".join(lines)


def append_trade_plan_record(path: Path, plan: TradePlan) -> None:
    append_jsonl(path, plan.to_dict())
