from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any

from quant_system.optimizer.health_labels import alert_reasons_text


@dataclass(frozen=True)
class StrategyConstraintPolicy:
    strategy: str
    state: str
    action: str
    alert_level: str
    exposure_multiplier: float
    recent_warn_count: int
    recent_block_count: int
    alerts: list[str]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_strategy_constraint_policy(
    strategy_health: dict[str, Any] | None,
    constraint_records: list[dict[str, Any]],
    *,
    strategy: str = "",
    as_of: date | None = None,
    window_days: int = 5,
    cooldown_block_count: int = 2,
    single_block_pause: int = 1,
    warn_escalation_count: int = 2,
    recover_after_clean_days: int = 3,
    warn_exposure_multiplier: float = 0.5,
) -> StrategyConstraintPolicy:
    strategy_name = str(strategy or (strategy_health or {}).get("strategy", "") or "").strip()
    recent = _recent_strategy_records(constraint_records, strategy_name, as_of=as_of, window_days=window_days)
    warn_count = sum(1 for item in recent if str(item.get("alert_level", "")) == "warn")
    block_count = sum(1 for item in recent if str(item.get("alert_level", "")) == "block")
    alert_counts: Counter[str] = Counter()
    for item in recent:
        alert_counts.update(str(alert) for alert in item.get("alerts", []) or [] if str(alert))
    base_alert = str((strategy_health or {}).get("alert_level", "pass") or "pass")
    base_action = str((strategy_health or {}).get("action", "keep") or "keep")
    top_alerts = [item for item, _count in alert_counts.most_common(3)]

    if block_count >= cooldown_block_count:
        return StrategyConstraintPolicy(
            strategy_name,
            "cooldown",
            "pause",
            "block",
            0.0,
            warn_count,
            block_count,
            _merge_alerts(top_alerts, "constraint_cooldown"),
            f"近{window_days}日触发 {block_count} 次阻断，进入冷静期：暂停新增仓位，至少等待连续{recover_after_clean_days}日无阻断后再恢复试仓。",
        )
    if block_count >= single_block_pause:
        return StrategyConstraintPolicy(
            strategy_name,
            "blocked",
            "pause",
            "block",
            0.0,
            warn_count,
            block_count,
            _merge_alerts(top_alerts, "constraint_cooldown"),
            f"近{window_days}日出现阻断记录，明日先暂停新增仓位；连续{recover_after_clean_days}日无阻断后再恢复试仓。复盘触发原因：{alert_reasons_text(top_alerts)}。",
        )
    if warn_count >= warn_escalation_count:
        return StrategyConstraintPolicy(
            strategy_name,
            "repeated_warn",
            "reduce",
            "warn",
            warn_exposure_multiplier,
            warn_count,
            block_count,
            _merge_alerts(top_alerts, "repeated_warn"),
            f"近{window_days}日连续预警 {warn_count} 次，明日只允许半仓上限和计划内交易。",
        )
    if warn_count > 0 or base_alert == "warn":
        alerts = top_alerts or list((strategy_health or {}).get("alerts", []) or [])
        return StrategyConstraintPolicy(
            strategy_name,
            "watch",
            "reduce" if base_action != "pause" else "pause",
            "warn",
            warn_exposure_multiplier,
            warn_count,
            block_count,
            _merge_alerts(alerts, "recovery_probe"),
            f"策略处于预警观察，明日降半档执行；连续{recover_after_clean_days}日无新增约束后恢复正常仓位。",
        )
    if base_alert == "block" or base_action == "pause":
        return StrategyConstraintPolicy(
            strategy_name,
            "blocked",
            "pause",
            "block",
            0.0,
            warn_count,
            block_count,
            _merge_alerts(list((strategy_health or {}).get("alerts", []) or []), "constraint_cooldown"),
            "策略健康度仍为阻断状态，明日暂停新增仓位。",
        )

    return StrategyConstraintPolicy(
        strategy_name,
        "normal",
        base_action,
        "pass",
        1.0,
        warn_count,
        block_count,
        [],
        f"近{window_days}日无策略约束触发，可按市场温度和候选质量正常执行。",
    )


def apply_constraint_policy_to_health(
    strategy_health: dict[str, Any],
    constraint_records: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    window_days: int = 5,
    cooldown_block_count: int = 2,
    single_block_pause: int = 1,
    warn_escalation_count: int = 2,
    recover_after_clean_days: int = 3,
    warn_exposure_multiplier: float = 0.5,
) -> dict[str, Any]:
    policy = build_strategy_constraint_policy(
        strategy_health,
        constraint_records,
        as_of=as_of,
        window_days=window_days,
        cooldown_block_count=cooldown_block_count,
        single_block_pause=single_block_pause,
        warn_escalation_count=warn_escalation_count,
        recover_after_clean_days=recover_after_clean_days,
        warn_exposure_multiplier=warn_exposure_multiplier,
    )
    adjusted = dict(strategy_health)
    adjusted["constraint_policy_config"] = {
        "window_days": window_days,
        "cooldown_block_count": cooldown_block_count,
        "single_block_pause": single_block_pause,
        "warn_escalation_count": warn_escalation_count,
        "recover_after_clean_days": recover_after_clean_days,
        "warn_exposure_multiplier": warn_exposure_multiplier,
    }
    adjusted["constraint_policy"] = policy.to_dict()
    adjusted["policy_state"] = policy.state
    adjusted["policy_note"] = policy.note
    adjusted["policy_exposure_multiplier"] = policy.exposure_multiplier
    trade_plan_audit = dict(adjusted.get("trade_plan_audit") or {})
    if trade_plan_audit:
        adjusted["policy_trade_plan_match_rate"] = float(trade_plan_audit.get("match_rate", 0) or 0)
        adjusted["policy_trade_plan_avg_price_deviation_pct"] = float(trade_plan_audit.get("avg_price_deviation_pct", 0) or 0)
        if float(trade_plan_audit.get("match_rate", 0) or 0) < 0.85:
            adjusted["policy_exposure_multiplier"] = min(float(adjusted.get("policy_exposure_multiplier", 1.0) or 1.0), warn_exposure_multiplier)
            adjusted["alerts"] = _merge_alerts(list(adjusted.get("alerts", []) or []), "trade_plan_drift")
        adjusted["policy_note"] = f"{policy.note}；计划命中率 {float(trade_plan_audit.get('match_rate', 0) or 0):.1%}"
    if _alert_rank(policy.alert_level) > _alert_rank(str(adjusted.get("alert_level", "pass"))):
        adjusted["alert_level"] = policy.alert_level
    if policy.action in {"pause", "reduce"}:
        adjusted["action"] = policy.action
    adjusted["alerts"] = _merge_alerts(list(adjusted.get("alerts", []) or []), *policy.alerts)
    return adjusted


def _recent_strategy_records(
    records: list[dict[str, Any]],
    strategy: str,
    *,
    as_of: date | None,
    window_days: int,
) -> list[dict[str, Any]]:
    dated = [(record, _record_date(record)) for record in records if _record_date(record)]
    if not dated:
        return []
    end = as_of or max(item_date for _record, item_date in dated if item_date is not None)
    start = end - timedelta(days=max(window_days - 1, 0))
    return [
        record
        for record, item_date in dated
        if item_date is not None
        and start <= item_date <= end
        and (not strategy or str(record.get("strategy", "")).strip() == strategy)
    ]


def _record_date(record: dict[str, Any]) -> date | None:
    value = str(record.get("created_at") or record.get("date") or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.fromisoformat(value[:10]).date()
        except ValueError:
            return None


def _merge_alerts(alerts: list[str], *extra: str) -> list[str]:
    result: list[str] = []
    for item in [*alerts, *extra]:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result


def _alert_rank(level: str) -> int:
    return {"pass": 0, "warn": 1, "block": 2}.get(level, 0)
