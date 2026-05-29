from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def summarize_trade_plan_audit(
    plan_records: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    limit: int = 20,
    *,
    include_by_strategy: bool = True,
) -> dict[str, Any]:
    plan_index = _bucket_by_key(plan_records)
    trade_index = _bucket_by_key(trade_records)

    matched: list[dict[str, Any]] = []
    unmatched_plans: list[dict[str, Any]] = []
    orphan_trades: list[dict[str, Any]] = []
    used_trades: set[tuple[tuple[str, str], int]] = set()
    price_deviations: list[float] = []
    planned_pct_gaps: list[float] = []
    amount_gaps: list[float] = []
    status_counts: Counter[str] = Counter()
    gate_counts: Counter[str] = Counter()

    for key, plans in plan_index.items():
        trades = trade_index.get(key, [])
        for idx, plan in enumerate(plans):
            status_counts[str(plan.get("status", "") or "")] += 1
            gate_counts[str(plan.get("gate_status", "") or "")] += 1
            trade = trades[idx] if idx < len(trades) else None
            if trade is None:
                unmatched_plans.append(plan)
                continue
            used_trades.add((key, idx))
            match = _build_match(plan, trade)
            matched.append(match)
            if match.get("execution_deviation_pct") is not None:
                price_deviations.append(float(match["execution_deviation_pct"]))
            if match.get("planned_pct_gap") is not None:
                planned_pct_gaps.append(float(match["planned_pct_gap"]))
            if match.get("amount_gap_pct") is not None:
                amount_gaps.append(float(match["amount_gap_pct"]))

    for key, trades in trade_index.items():
        for idx, trade in enumerate(trades):
            if (key, idx) in used_trades:
                continue
            if _looks_related(trade):
                orphan_trades.append(trade)

    visible_limit = max(int(limit), 0)
    summary = {
        "total_plans": len(plan_records),
        "matched_trades": len(matched),
        "unmatched_plans": len(unmatched_plans),
        "orphan_trades": len(orphan_trades),
        "match_rate": len(matched) / len(plan_records) if plan_records else 0.0,
        "avg_price_deviation_pct": _mean(price_deviations),
        "avg_planned_pct_gap": _mean(planned_pct_gaps),
        "avg_amount_gap_pct": _mean(amount_gaps),
        "status_counts": dict(status_counts),
        "gate_counts": dict(gate_counts),
        "latest_matches": matched[-visible_limit:] if visible_limit else matched,
        "latest_unmatched_plans": unmatched_plans[-visible_limit:] if visible_limit else unmatched_plans,
        "latest_orphan_trades": orphan_trades[-visible_limit:] if visible_limit else orphan_trades,
        "action_items": _action_items(
            total_plans=len(plan_records),
            matched_trades=len(matched),
            unmatched_plans=len(unmatched_plans),
            orphan_trades=len(orphan_trades),
            avg_price_deviation_pct=_mean(price_deviations),
        ),
    }
    if include_by_strategy:
        summary["by_strategy"] = _summarize_audit_by_strategy(plan_records, trade_records, limit=limit)
    return summary


def render_trade_plan_audit_lines(summary: dict | None) -> list[str]:
    if not summary or int(summary.get("total_plans", 0) or 0) == 0:
        return ["- 暂无计划单验证记录。先生成 trade plan，再记录实际交易。"]

    lines = [
        f"- 计划单总数：{int(summary.get('total_plans', 0) or 0)}",
        f"- 命中交易数：{int(summary.get('matched_trades', 0) or 0)}",
        f"- 未命中计划：{int(summary.get('unmatched_plans', 0) or 0)}",
        f"- 孤儿交易：{int(summary.get('orphan_trades', 0) or 0)}",
        f"- 命中率：{float(summary.get('match_rate', 0) or 0):.1%}",
        f"- 平均价格偏差：{float(summary.get('avg_price_deviation_pct', 0) or 0):.2%}",
        f"- 平均计划仓位偏差：{float(summary.get('avg_planned_pct_gap', 0) or 0):.2%}",
        f"- 平均金额偏差：{float(summary.get('avg_amount_gap_pct', 0) or 0):.2%}",
    ]

    if summary.get("status_counts"):
        lines.append(
            "- 计划状态分布："
            + ", ".join(f"{key or 'unknown'}={int(value)}" for key, value in sorted(summary["status_counts"].items()))
        )
    if summary.get("gate_counts"):
        lines.append(
            "- 门禁状态分布："
            + ", ".join(f"{key or 'unknown'}={int(value)}" for key, value in sorted(summary["gate_counts"].items()))
        )

    matches = list(summary.get("latest_matches", []) or [])
    if matches:
        lines.extend(
            [
                "",
                "## 最近命中",
                "",
                "| Date | Symbol | Plan | Trade | ExecDev | PlanGap | AmountGap |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in matches:
            lines.append(
                f"| {item.get('trade_date', '')} | {item.get('symbol', '')} | "
                f"{float(item.get('planned_price', 0) or 0):.2f} | {float(item.get('trade_price', 0) or 0):.2f} | "
                f"{float(item.get('execution_deviation_pct', 0) or 0):.2%} | "
                f"{float(item.get('planned_pct_gap', 0) or 0):.2%} | "
                f"{float(item.get('amount_gap_pct', 0) or 0):.2%} |"
            )

    plans = list(summary.get("latest_unmatched_plans", []) or [])
    if plans:
        lines.extend(["", "## 未命中计划", ""])
        for plan in plans:
            lines.append(f"- {plan.get('trade_date', '')} {plan.get('symbol', '')} {plan.get('gate_status', '')} {plan.get('status', '')}")

    trades = list(summary.get("latest_orphan_trades", []) or [])
    if trades:
        lines.extend(["", "## 孤儿交易", ""])
        for trade in trades:
            lines.append(f"- {trade.get('date', '')} {trade.get('symbol', '')} {trade.get('side', '')} {trade.get('gate_status', '')}")

    action_items = list(summary.get("action_items", []) or [])
    if action_items:
        lines.extend(["", "## 行动项", ""])
        lines.extend(f"- {item}" for item in action_items)
    return lines


def render_trade_plan_audit_markdown(summary: dict | None) -> str:
    return "\n".join(["# 计划-成交审计", "", *render_trade_plan_audit_lines(summary), ""])


def apply_trade_plan_audit_to_health(strategy_health: dict[str, Any], audit_summary: dict | None) -> dict[str, Any]:
    adjusted = dict(strategy_health)
    audit_summary = audit_summary or {}
    if not audit_summary or int(audit_summary.get("total_plans", 0) or 0) == 0:
        return adjusted

    match_rate = float(audit_summary.get("match_rate", 0) or 0)
    avg_price_deviation_pct = float(audit_summary.get("avg_price_deviation_pct", 0) or 0)
    unmatched_plans = int(audit_summary.get("unmatched_plans", 0) or 0)
    orphan_trades = int(audit_summary.get("orphan_trades", 0) or 0)

    adjusted["trade_plan_match_rate"] = match_rate
    adjusted["trade_plan_avg_price_deviation_pct"] = avg_price_deviation_pct
    adjusted["trade_plan_unmatched_count"] = unmatched_plans
    adjusted["trade_plan_orphan_count"] = orphan_trades
    adjusted["trade_plan_audit"] = {
        "total_plans": int(audit_summary.get("total_plans", 0) or 0),
        "matched_trades": int(audit_summary.get("matched_trades", 0) or 0),
        "unmatched_plans": unmatched_plans,
        "orphan_trades": orphan_trades,
        "match_rate": match_rate,
        "avg_price_deviation_pct": avg_price_deviation_pct,
    }

    alerts = list(adjusted.get("alerts", []) or [])
    if match_rate < 0.7 or orphan_trades >= 2 or unmatched_plans >= 3:
        adjusted["alert_level"] = "block"
        adjusted["action"] = "pause"
        alerts = _merge_unique(alerts, "trade_plan_mismatch", "trade_plan_block")
    elif match_rate < 0.85 or abs(avg_price_deviation_pct) > 0.03 or unmatched_plans > 0:
        if _alert_rank(str(adjusted.get("alert_level", "pass"))) < _alert_rank("warn"):
            adjusted["alert_level"] = "warn"
        if str(adjusted.get("action", "keep")) != "pause":
            adjusted["action"] = "reduce"
        alerts = _merge_unique(alerts, "trade_plan_drift")
    adjusted["alerts"] = alerts
    adjusted["trade_plan_note"] = _trade_plan_note(audit_summary)
    return adjusted


def _summarize_audit_by_strategy(
    plan_records: list[dict[str, Any]],
    trade_records: list[dict[str, Any]],
    *,
    limit: int,
) -> dict[str, dict[str, Any]]:
    strategies = sorted(
        {
            str(item.get("strategy", "")).strip()
            for item in [*plan_records, *trade_records]
            if str(item.get("strategy", "")).strip()
        }
    )
    return {
        strategy: summarize_trade_plan_audit(
            [record for record in plan_records if str(record.get("strategy", "")).strip() == strategy],
            [record for record in trade_records if str(record.get("strategy", "")).strip() == strategy],
            limit=limit,
            include_by_strategy=False,
        )
        for strategy in strategies
    }


def _bucket_by_key(records: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (_record_date(record), _record_symbol(record))
        if not key[0] or not key[1]:
            continue
        buckets[key].append(record)
    return buckets


def _build_match(plan: dict[str, Any], trade: dict[str, Any]) -> dict[str, Any]:
    planned_price = _float_or_none(plan.get("entry_price"))
    trade_price = _float_or_none(trade.get("price"))
    planned_pct = _float_or_none(plan.get("planned_pct"))
    trade_planned_pct = _float_or_none(trade.get("planned_pct"))
    amount = _float_or_none(trade.get("amount"))
    planned_value = _float_or_none(plan.get("planned_value"))
    execution_deviation_pct = None
    amount_gap_pct = None
    planned_pct_gap = None
    if planned_price not in (None, 0) and trade_price is not None:
        execution_deviation_pct = trade_price / planned_price - 1.0
    if planned_pct is not None and trade_planned_pct is not None:
        planned_pct_gap = trade_planned_pct - planned_pct
    if planned_value not in (None, 0) and amount is not None:
        amount_gap_pct = amount / planned_value - 1.0
    return {
        "trade_date": _record_date(plan),
        "symbol": _record_symbol(plan),
        "gate_status": str(plan.get("gate_status", "") or ""),
        "status": str(plan.get("status", "") or ""),
        "planned_price": planned_price or 0.0,
        "trade_price": trade_price or 0.0,
        "execution_deviation_pct": execution_deviation_pct,
        "planned_pct_gap": planned_pct_gap,
        "amount_gap_pct": amount_gap_pct,
        "discipline_exception": bool(plan.get("discipline_exception") or trade.get("discipline_exception")),
        "exception_reason": str(trade.get("exception_reason", plan.get("exception_reason", "")) or ""),
    }


def _record_date(record: dict[str, Any]) -> str:
    return str(record.get("trade_date", record.get("date", "")) or "").strip()


def _record_symbol(record: dict[str, Any]) -> str:
    return str(record.get("symbol", "") or "").strip().zfill(6)


def _looks_related(record: dict[str, Any]) -> bool:
    tags = record.get("tags", [])
    if isinstance(tags, list) and "trade-plan" in [str(tag) for tag in tags]:
        return True
    return bool(record.get("planned_price") or record.get("planned_pct") or record.get("gate_status"))


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _action_items(
    *,
    total_plans: int,
    matched_trades: int,
    unmatched_plans: int,
    orphan_trades: int,
    avg_price_deviation_pct: float,
) -> list[str]:
    items: list[str] = []
    if unmatched_plans:
        items.append("部分计划买入没有对应成交；盘后需要标记为过期、取消或跳过。")
    if orphan_trades:
        items.append("部分成交没有匹配计划；新增买入前必须先生成并留存计划单。")
    if matched_trades and abs(avg_price_deviation_pct) > 0.02:
        items.append("平均执行偏差超过 2%；需要收窄执行价格窗口或降低追价急迫度。")
    if not items:
        items.append("当前样本计划-成交链路干净；继续保持每笔 BUY 都绑定计划单。")
    return items


def _merge_unique(values: list[str], *extra: str) -> list[str]:
    result: list[str] = []
    for item in [*values, *extra]:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result


def _alert_rank(level: str) -> int:
    return {"pass": 0, "warn": 1, "block": 2}.get(level, 0)


def _trade_plan_note(audit_summary: dict[str, Any]) -> str:
    return (
        f"计划命中率 {float(audit_summary.get('match_rate', 0) or 0):.1%}，"
        f"平均执行偏差 {float(audit_summary.get('avg_price_deviation_pct', 0) or 0):.2%}"
    )
