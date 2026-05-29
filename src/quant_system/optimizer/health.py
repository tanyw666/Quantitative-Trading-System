from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyHealth:
    strategy: str
    selection_count: int
    trade_count: int
    promotion_count: int
    promotion_ok_count: int
    promotion_backtest_count: int
    latest_selection_date: str | None
    latest_trade_date: str | None
    latest_promotion_at: str | None
    avg_selection_close: float | None
    gross_buy_amount: float
    gross_sell_amount: float
    net_realized_amount: float
    win_rate: float | None
    avg_execution_deviation_pct: float | None
    trade_plan_match_rate: float | None
    trade_plan_unmatched_count: int
    trade_plan_orphan_count: int
    trade_plan_avg_price_deviation_pct: float | None
    trade_plan_audit: dict[str, Any]
    lifecycle_pressure: dict[str, Any]
    mistake_count: int
    top_mistake: str | None
    top_tag: str | None
    alert_level: str
    alerts: list[str]
    promotion_success_rate: float | None
    score: float
    status: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_strategy_health(
    selections: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
    trade_plan_audits: dict[str, dict[str, Any]] | None = None,
    lifecycle_pressure: dict[str, Any] | None = None,
) -> list[StrategyHealth]:
    strategies = sorted(
        {
            _strategy_name(item)
            for item in [*selections, *trades, *promotions]
            if _strategy_name(item)
        }
    )
    results: list[StrategyHealth] = []
    for strategy in strategies:
        strategy_selections = [item for item in selections if _strategy_name(item) == strategy]
        strategy_trades = [item for item in trades if _strategy_name(item) == strategy]
        strategy_promotions = [item for item in promotions if _strategy_name(item) == strategy]

        selection_count = len(strategy_selections)
        trade_count = len(strategy_trades)
        promotion_count = len(strategy_promotions)
        promotion_ok_count = sum(1 for item in strategy_promotions if item.get("ok"))
        promotion_backtest_count = sum(1 for item in strategy_promotions if item.get("backtest"))

        latest_selection_date = _latest_text(strategy_selections, "date")
        latest_trade_date = _latest_text(strategy_trades, "date")
        latest_promotion_at = _latest_text(strategy_promotions, "created_at")
        avg_selection_close = _mean([_as_float(item.get("close")) for item in strategy_selections])
        gross_buy_amount, gross_sell_amount = _gross_amounts(strategy_trades)
        net_realized_amount = _net_realized_amount(strategy_trades)
        win_rate = _win_rate(strategy_trades)
        avg_execution_deviation_pct = _avg_execution_deviation(strategy_trades)
        mistake_count = _mistake_count(strategy_trades)
        top_mistake = _top_mistake(strategy_trades)
        top_tag = _top_tag(strategy_trades)
        alerts = _build_alerts(
            trade_count=trade_count,
            net_realized_amount=net_realized_amount,
            win_rate=win_rate,
            avg_execution_deviation_pct=avg_execution_deviation_pct,
            mistake_count=mistake_count,
            top_mistake=top_mistake,
            top_tag=top_tag,
        )
        alert_level = _alert_level(alerts)
        promotion_success_rate = (
            promotion_ok_count / promotion_count if promotion_count else None
        )
        audit_summary = (trade_plan_audits or {}).get(strategy, {})
        trade_plan_match_rate = _float_or_none(audit_summary.get("match_rate"))
        trade_plan_unmatched_count = int(audit_summary.get("unmatched_plans", 0) or 0)
        trade_plan_orphan_count = int(audit_summary.get("orphan_trades", 0) or 0)
        trade_plan_avg_price_deviation_pct = _float_or_none(audit_summary.get("avg_price_deviation_pct"))
        score = _score_strategy(
            selection_count=selection_count,
            trade_count=trade_count,
            promotion_success_rate=promotion_success_rate,
            win_rate=win_rate,
            avg_execution_deviation_pct=avg_execution_deviation_pct,
            mistake_count=mistake_count,
            top_mistake=top_mistake,
            top_tag=top_tag,
            promotion_backtest_count=promotion_backtest_count,
            net_realized_amount=net_realized_amount,
            trade_plan_audit=audit_summary,
        )
        status, action = _classify_score(score)
        action = _action_with_alerts(action, alert_level)
        action, alert_level, alerts, score = _apply_trade_plan_audit_feedback(
            action=action,
            alert_level=alert_level,
            alerts=alerts,
            score=score,
            audit_summary=audit_summary,
        )
        action, alert_level, alerts, score = _apply_lifecycle_pressure_feedback(
            action=action,
            alert_level=alert_level,
            alerts=alerts,
            score=score,
            pressure=lifecycle_pressure,
        )
        status, base_action = _classify_score(score)
        if action not in {"pause", "reduce"}:
            action = _action_with_alerts(base_action, alert_level)
        results.append(
            StrategyHealth(
                strategy=strategy,
                selection_count=selection_count,
                trade_count=trade_count,
                promotion_count=promotion_count,
                promotion_ok_count=promotion_ok_count,
                promotion_backtest_count=promotion_backtest_count,
                latest_selection_date=latest_selection_date,
                latest_trade_date=latest_trade_date,
                latest_promotion_at=latest_promotion_at,
                avg_selection_close=avg_selection_close,
                gross_buy_amount=gross_buy_amount,
                gross_sell_amount=gross_sell_amount,
                net_realized_amount=net_realized_amount,
                win_rate=win_rate,
                avg_execution_deviation_pct=avg_execution_deviation_pct,
                trade_plan_match_rate=trade_plan_match_rate,
                trade_plan_unmatched_count=trade_plan_unmatched_count,
                trade_plan_orphan_count=trade_plan_orphan_count,
                trade_plan_avg_price_deviation_pct=trade_plan_avg_price_deviation_pct,
                trade_plan_audit=audit_summary,
                lifecycle_pressure=lifecycle_pressure or {},
                mistake_count=mistake_count,
                top_mistake=top_mistake,
                top_tag=top_tag,
                alert_level=alert_level,
                alerts=alerts,
                promotion_success_rate=promotion_success_rate,
                score=score,
                status=status,
                action=action,
            )
        )
    return sorted(results, key=lambda item: (-item.score, item.strategy))


def _latest_text(records: list[dict[str, Any]], key: str) -> str | None:
    values = [str(item.get(key, "")).strip() for item in records if str(item.get(key, "")).strip()]
    return max(values) if values else None


def _strategy_name(record: dict[str, Any]) -> str:
    return str(record.get("strategy") or record.get("strategy_name") or "").strip()


def _mean(values: list[float | None]) -> float | None:
    usable = [value for value in values if value is not None]
    if not usable:
        return None
    return sum(usable) / len(usable)


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _net_realized_amount(trades: list[dict[str, Any]]) -> float:
    total = 0.0
    for item in trades:
        amount = float(item.get("amount", 0) or 0)
        side = str(item.get("side", "")).upper()
        total += amount if side == "SELL" else -amount
    return total


def _gross_amounts(trades: list[dict[str, Any]]) -> tuple[float, float]:
    gross_buy = 0.0
    gross_sell = 0.0
    for item in trades:
        amount = float(item.get("amount", 0) or 0)
        side = str(item.get("side", "")).upper()
        if side == "BUY":
            gross_buy += amount
        elif side == "SELL":
            gross_sell += amount
    return gross_buy, gross_sell


def _win_rate(trades: list[dict[str, Any]]) -> float | None:
    closed = [item for item in trades if str(item.get("side", "")).upper() == "SELL"]
    if not closed:
        return None
    wins = 0
    for item in closed:
        deviation = item.get("execution_deviation_pct")
        if deviation is not None and float(deviation) >= 0:
            wins += 1
            continue
        reason = str(item.get("reason", ""))
        if "止盈" in reason or "take" in reason.lower():
            wins += 1
    return wins / len(closed)


def _avg_execution_deviation(trades: list[dict[str, Any]]) -> float | None:
    deviations = [
        float(item.get("execution_deviation_pct"))
        for item in trades
        if item.get("execution_deviation_pct") not in (None, "")
    ]
    return (sum(deviations) / len(deviations)) if deviations else None


def _mistake_count(trades: list[dict[str, Any]]) -> int:
    return sum(1 for item in trades if str(item.get("mistake_type", "")).strip())


def _top_mistake(trades: list[dict[str, Any]]) -> str | None:
    counts = Counter(
        str(item.get("mistake_type", "")).strip()
        for item in trades
        if str(item.get("mistake_type", "")).strip()
    )
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _top_tag(trades: list[dict[str, Any]]) -> str | None:
    counts: Counter[str] = Counter()
    for item in trades:
        tags = item.get("tags", [])
        if isinstance(tags, str):
            tags = [part.strip() for part in tags.split(",") if part.strip()]
        counts.update(str(tag).strip() for tag in tags if str(tag).strip())
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _score_strategy(
    *,
    selection_count: int,
    trade_count: int,
    promotion_success_rate: float | None,
    win_rate: float | None,
    avg_execution_deviation_pct: float | None,
    mistake_count: int,
    top_mistake: str | None,
    top_tag: str | None,
    promotion_backtest_count: int,
    net_realized_amount: float,
    trade_plan_audit: dict[str, Any] | None = None,
) -> float:
    score = 50.0
    score += min(selection_count, 20) * 0.8
    score += min(trade_count, 20) * 1.2
    score += min(promotion_backtest_count, 5) * 4.0
    score += (promotion_success_rate or 0.0) * 20.0
    score += (win_rate or 0.0) * 20.0
    if avg_execution_deviation_pct is not None:
        score -= min(abs(avg_execution_deviation_pct) * 200.0, 12.0)
    score -= min(mistake_count * 2.5, 12.0)
    if top_mistake:
        score -= 1.5
    if top_tag in {"计划内", "止盈", "止损"}:
        score += 1.0
    if net_realized_amount > 0:
        score += min(net_realized_amount / 2000.0, 10.0)
    elif net_realized_amount < 0:
        score -= min(abs(net_realized_amount) / 2000.0, 15.0)
    audit_summary = trade_plan_audit or {}
    if audit_summary:
        match_rate = float(audit_summary.get("match_rate", 0) or 0)
        avg_price_deviation_pct = abs(float(audit_summary.get("avg_price_deviation_pct", 0) or 0))
        unmatched_plans = int(audit_summary.get("unmatched_plans", 0) or 0)
        orphan_trades = int(audit_summary.get("orphan_trades", 0) or 0)
        score += match_rate * 10.0
        score -= min(avg_price_deviation_pct * 200.0, 10.0)
        score -= min(unmatched_plans * 2.0 + orphan_trades * 3.0, 12.0)
    return round(max(score, 0.0), 2)


def _build_alerts(
    *,
    trade_count: int,
    net_realized_amount: float,
    win_rate: float | None,
    avg_execution_deviation_pct: float | None,
    mistake_count: int,
    top_mistake: str | None,
    top_tag: str | None,
) -> list[str]:
    alerts: list[str] = []
    if avg_execution_deviation_pct is not None and abs(avg_execution_deviation_pct) >= 0.03:
        alerts.append("execution_deviation")
    if mistake_count >= 3 or (trade_count >= 4 and mistake_count / trade_count >= 0.5):
        alerts.append("mistake_cluster")
    if top_mistake in {"追高", "不止损", "情绪单"}:
        alerts.append("behavior_mistake")
    if top_tag in {"情绪单", "冲动交易", "追高"}:
        alerts.append("emotion_tag")
    if trade_count >= 2 and net_realized_amount < 0:
        alerts.append("negative_flow")
    if win_rate is not None and win_rate < 0.4:
        alerts.append("low_win_rate")
    return alerts


def _alert_level(alerts: list[str]) -> str:
    if len(alerts) >= 2:
        return "block"
    if alerts:
        return "warn"
    return "pass"


def _classify_score(score: float) -> tuple[str, str]:
    if score >= 80:
        return "strong", "increase"
    if score >= 65:
        return "watch", "keep"
    return "weak", "reduce"


def _apply_trade_plan_audit_feedback(
    *,
    action: str,
    alert_level: str,
    alerts: list[str],
    score: float,
    audit_summary: dict[str, Any] | None,
) -> tuple[str, str, list[str], float]:
    audit_summary = audit_summary or {}
    if not audit_summary:
        return action, alert_level, alerts, score
    match_rate = float(audit_summary.get("match_rate", 0) or 0)
    avg_price_deviation_pct = abs(float(audit_summary.get("avg_price_deviation_pct", 0) or 0))
    unmatched_plans = int(audit_summary.get("unmatched_plans", 0) or 0)
    orphan_trades = int(audit_summary.get("orphan_trades", 0) or 0)
    if match_rate < 0.7 or orphan_trades >= 2:
        alert_level = "block"
        action = "pause"
        score = max(score - 15.0, 0.0)
        alerts = _merge_alerts(alerts, "trade_plan_block")
    elif match_rate < 0.85 or avg_price_deviation_pct > 0.03 or unmatched_plans > 0:
        if _alert_rank(alert_level) < _alert_rank("warn"):
            alert_level = "warn"
        if action != "pause":
            action = "reduce"
        score = max(score - 5.0, 0.0)
        alerts = _merge_alerts(alerts, "trade_plan_drift")
    return action, alert_level, alerts, score


def _apply_lifecycle_pressure_feedback(
    *,
    action: str,
    alert_level: str,
    alerts: list[str],
    score: float,
    pressure: dict[str, Any] | None,
) -> tuple[str, str, list[str], float]:
    pressure = pressure or {}
    if not pressure:
        return action, alert_level, alerts, score

    pressure_level = str(pressure.get("alert_level", "pass") or "pass")
    pressure_action = str(pressure.get("action", "keep") or "keep")
    pressure_score = pressure.get("score")
    pressure_alerts = [str(item) for item in pressure.get("alerts", []) or []]

    if pressure_score not in (None, ""):
        score = max(score - min((100.0 - float(pressure_score)) * 0.35, 20.0), 0.0)
    if _alert_rank(pressure_level) > _alert_rank(alert_level):
        alert_level = pressure_level
    if pressure_action == "pause":
        action = "pause"
    elif pressure_action == "reduce" and action != "pause":
        action = "reduce"
    alerts = _merge_alerts(alerts, *pressure_alerts)
    return action, alert_level, alerts, score


def _merge_alerts(alerts: list[str], *extra: str) -> list[str]:
    result: list[str] = []
    for item in [*alerts, *extra]:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result


def _alert_rank(level: str) -> int:
    return {"pass": 0, "warn": 1, "block": 2}.get(level, 0)


def _action_with_alerts(action: str, alert_level: str) -> str:
    if alert_level == "block":
        return "pause"
    if alert_level == "warn" and action == "increase":
        return "keep"
    return action
