from __future__ import annotations

from typing import Any


def normalize_trade_plan_pressure(*sources: dict | None) -> dict[str, Any] | None:
    for source in sources:
        pressure = _extract_trade_plan_pressure(source)
        if pressure:
            return pressure
    return None


def format_trade_plan_pressure(pressure: dict | None) -> str:
    if not pressure:
        return ""

    parts: list[str] = []
    match_rate = pressure.get("match_rate")
    unmatched_plans = pressure.get("unmatched_plans")
    orphan_trades = pressure.get("orphan_trades")
    avg_price_deviation_pct = pressure.get("avg_price_deviation_pct")
    score = pressure.get("score")
    status = str(pressure.get("status", "") or "").strip()

    if match_rate not in (None, ""):
        parts.append(f"命中率 {float(match_rate):.1%}")
    if unmatched_plans not in (None, ""):
        parts.append(f"失配 {int(unmatched_plans)}")
    if orphan_trades not in (None, ""):
        parts.append(f"孤儿成交 {int(orphan_trades)}")
    if avg_price_deviation_pct not in (None, ""):
        parts.append(f"平均偏差 {float(avg_price_deviation_pct):.2%}")
    if score not in (None, ""):
        parts.append(f"评分 {float(score):.1f}")
    if status:
        parts.append(f"状态 {status}")
    return "；".join(parts)


def _extract_trade_plan_pressure(source: dict | None) -> dict[str, Any] | None:
    if not source:
        return None
    audit = source.get("trade_plan_audit")
    if isinstance(audit, dict) and audit:
        return dict(audit)

    pressure = {
        "match_rate": source.get("match_rate", source.get("trade_plan_match_rate")),
        "unmatched_plans": source.get("unmatched_plans", source.get("trade_plan_unmatched_count")),
        "orphan_trades": source.get("orphan_trades", source.get("trade_plan_orphan_count")),
        "avg_price_deviation_pct": source.get(
            "avg_price_deviation_pct", source.get("trade_plan_avg_price_deviation_pct")
        ),
        "score": source.get("score", source.get("trade_plan_score")),
        "status": source.get("status", source.get("trade_plan_status")),
        "action": source.get("action", source.get("trade_plan_action")),
    }
    if any(value not in (None, "", [], {}) for value in pressure.values()):
        return pressure
    return None
