from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
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
    clean_days: int = 0
    last_constraint_date: str = ""
    recovery_ready: bool = False
    recovery_reasons: list[str] = field(default_factory=list)

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
    recover_probe_days: int = 2,
    recover_probe_exposure_multiplier: float = 0.25,
    recover_trade_plan_match_rate_min: float = 0.9,
    recover_max_unmatched_plans: int = 0,
    recover_max_orphan_trades: int = 0,
    warn_exposure_multiplier: float = 0.5,
) -> StrategyConstraintPolicy:
    strategy_name = str(strategy or (strategy_health or {}).get("strategy", "") or "").strip()
    end = as_of or date.today()
    recent = _recent_strategy_records(constraint_records, strategy_name, as_of=end, window_days=window_days)
    warn_count = sum(1 for item in recent if str(item.get("alert_level", "")) == "warn")
    block_count = sum(1 for item in recent if str(item.get("alert_level", "")) == "block")
    alert_counts: Counter[str] = Counter()
    for item in recent:
        alert_counts.update(str(alert) for alert in item.get("alerts", []) or [] if str(alert))

    base_alert = str((strategy_health or {}).get("alert_level", "pass") or "pass")
    base_action = str((strategy_health or {}).get("action", "keep") or "keep")
    top_alerts = [item for item, _count in alert_counts.most_common(3)]
    history = _dated_strategy_records(constraint_records, strategy_name)
    restrictive_dates = [
        item_date
        for item, item_date in history
        if item_date is not None and item_date <= end and str(item.get("alert_level", "")) in {"warn", "block"}
    ]
    last_constraint_date = max(restrictive_dates) if restrictive_dates else None
    clean_days = (end - last_constraint_date).days if last_constraint_date else 0
    recovery = _recovery_evidence(
        strategy_health,
        match_rate_min=recover_trade_plan_match_rate_min,
        max_unmatched_plans=recover_max_unmatched_plans,
        max_orphan_trades=recover_max_orphan_trades,
    )
    last_date_text = last_constraint_date.isoformat() if last_constraint_date else ""

    if restrictive_dates and clean_days >= recover_after_clean_days and recovery["ready"]:
        if clean_days >= recover_after_clean_days + max(recover_probe_days, 0):
            return StrategyConstraintPolicy(
                strategy=strategy_name,
                state="recovered",
                action="keep",
                alert_level="pass",
                exposure_multiplier=1.0,
                recent_warn_count=warn_count,
                recent_block_count=block_count,
                alerts=_merge_alerts(top_alerts, "constraint_recovered"),
                note=(
                    f"Recovery cleared after {clean_days} clean days since {last_date_text}; "
                    "normal sizing is restored."
                ),
                clean_days=clean_days,
                last_constraint_date=last_date_text,
                recovery_ready=True,
                recovery_reasons=list(recovery["reasons"]),
            )
        return StrategyConstraintPolicy(
            strategy=strategy_name,
            state="recovery_probe",
            action="reduce",
            alert_level="warn",
            exposure_multiplier=max(0.0, min(float(recover_probe_exposure_multiplier), 1.0)),
            recent_warn_count=warn_count,
            recent_block_count=block_count,
            alerts=_merge_alerts(top_alerts, "recovery_probe"),
            note=(
                f"Recovery probe enabled after {clean_days} clean days since {last_date_text}; "
                f"use reduced size for {recover_probe_days} more clean days."
            ),
            clean_days=clean_days,
            last_constraint_date=last_date_text,
            recovery_ready=True,
            recovery_reasons=list(recovery["reasons"]),
        )

    if block_count >= cooldown_block_count:
        return StrategyConstraintPolicy(
            strategy=strategy_name,
            state="cooldown",
            action="pause",
            alert_level="block",
            exposure_multiplier=0.0,
            recent_warn_count=warn_count,
            recent_block_count=block_count,
            alerts=_merge_alerts(top_alerts, "constraint_cooldown"),
            note=(
                f"Blocked {block_count} times inside the last {window_days} days; "
                f"pause new BUY orders and wait for at least {recover_after_clean_days} clean days "
                f"(连续{recover_after_clean_days}日)."
            ),
            clean_days=clean_days,
            last_constraint_date=last_date_text,
            recovery_ready=False,
            recovery_reasons=list(recovery["reasons"]),
        )
    if block_count >= single_block_pause:
        return StrategyConstraintPolicy(
            strategy=strategy_name,
            state="blocked",
            action="pause",
            alert_level="block",
            exposure_multiplier=0.0,
            recent_warn_count=warn_count,
            recent_block_count=block_count,
            alerts=_merge_alerts(top_alerts, "constraint_cooldown"),
            note=(
                f"A block constraint was triggered within the last {window_days} days; "
                f"pause new BUY orders until at least {recover_after_clean_days} clean days have passed "
                f"(连续{recover_after_clean_days}日)."
            ),
            clean_days=clean_days,
            last_constraint_date=last_date_text,
            recovery_ready=False,
            recovery_reasons=list(recovery["reasons"]),
        )
    if warn_count >= warn_escalation_count:
        return StrategyConstraintPolicy(
            strategy=strategy_name,
            state="repeated_warn",
            action="reduce",
            alert_level="warn",
            exposure_multiplier=warn_exposure_multiplier,
            recent_warn_count=warn_count,
            recent_block_count=block_count,
            alerts=_merge_alerts(top_alerts, "repeated_warn"),
            note=(
                f"Warn constraints were triggered {warn_count} times in the last {window_days} days; "
                "reduce exposure and trade only inside the written plan."
            ),
            clean_days=clean_days,
            last_constraint_date=last_date_text,
            recovery_ready=False,
            recovery_reasons=list(recovery["reasons"]),
        )
    if warn_count > 0 or base_alert == "warn":
        alerts = top_alerts or list((strategy_health or {}).get("alerts", []) or [])
        return StrategyConstraintPolicy(
            strategy=strategy_name,
            state="watch",
            action="reduce" if base_action != "pause" else "pause",
            alert_level="warn",
            exposure_multiplier=warn_exposure_multiplier,
            recent_warn_count=warn_count,
            recent_block_count=block_count,
            alerts=_merge_alerts(alerts, "recovery_watch"),
            note=(
                f"Strategy is under warning watch; after {recover_after_clean_days} clean days "
                f"(连续{recover_after_clean_days}日) it may enter recovery-probe mode if the review evidence is clean."
            ),
            clean_days=clean_days,
            last_constraint_date=last_date_text,
            recovery_ready=False,
            recovery_reasons=list(recovery["reasons"]),
        )
    if base_alert == "block" or base_action == "pause":
        return StrategyConstraintPolicy(
            strategy=strategy_name,
            state="blocked",
            action="pause",
            alert_level="block",
            exposure_multiplier=0.0,
            recent_warn_count=warn_count,
            recent_block_count=block_count,
            alerts=_merge_alerts(list((strategy_health or {}).get("alerts", []) or []), "constraint_cooldown"),
            note="Strategy health is still blocked; do not open new BUY positions yet.",
            clean_days=clean_days,
            last_constraint_date=last_date_text,
            recovery_ready=False,
            recovery_reasons=list(recovery["reasons"]),
        )

    return StrategyConstraintPolicy(
        strategy=strategy_name,
        state="normal",
        action=base_action,
        alert_level="pass",
        exposure_multiplier=1.0,
        recent_warn_count=warn_count,
        recent_block_count=block_count,
        alerts=[],
        note=f"No active constraint in the last {window_days} days; normal execution is allowed.",
        clean_days=clean_days,
        last_constraint_date=last_date_text,
        recovery_ready=True,
        recovery_reasons=list(recovery["reasons"]),
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
    recover_probe_days: int = 2,
    recover_probe_exposure_multiplier: float = 0.25,
    recover_trade_plan_match_rate_min: float = 0.9,
    recover_max_unmatched_plans: int = 0,
    recover_max_orphan_trades: int = 0,
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
        recover_probe_days=recover_probe_days,
        recover_probe_exposure_multiplier=recover_probe_exposure_multiplier,
        recover_trade_plan_match_rate_min=recover_trade_plan_match_rate_min,
        recover_max_unmatched_plans=recover_max_unmatched_plans,
        recover_max_orphan_trades=recover_max_orphan_trades,
        warn_exposure_multiplier=warn_exposure_multiplier,
    )
    adjusted = dict(strategy_health)
    adjusted["constraint_policy_config"] = {
        "window_days": window_days,
        "cooldown_block_count": cooldown_block_count,
        "single_block_pause": single_block_pause,
        "warn_escalation_count": warn_escalation_count,
        "recover_after_clean_days": recover_after_clean_days,
        "recover_probe_days": recover_probe_days,
        "recover_probe_exposure_multiplier": recover_probe_exposure_multiplier,
        "recover_trade_plan_match_rate_min": recover_trade_plan_match_rate_min,
        "recover_max_unmatched_plans": recover_max_unmatched_plans,
        "recover_max_orphan_trades": recover_max_orphan_trades,
        "warn_exposure_multiplier": warn_exposure_multiplier,
    }
    adjusted["constraint_policy"] = policy.to_dict()
    adjusted["policy_state"] = policy.state
    adjusted["policy_note"] = policy.note
    adjusted["policy_exposure_multiplier"] = policy.exposure_multiplier
    adjusted["policy_clean_days"] = policy.clean_days
    adjusted["policy_last_constraint_date"] = policy.last_constraint_date
    adjusted["policy_recovery_ready"] = policy.recovery_ready
    adjusted["policy_recovery_reasons"] = list(policy.recovery_reasons)

    trade_plan_audit = dict(adjusted.get("trade_plan_audit") or {})
    if trade_plan_audit:
        adjusted["policy_trade_plan_match_rate"] = float(trade_plan_audit.get("match_rate", 0) or 0)
        adjusted["policy_trade_plan_avg_price_deviation_pct"] = float(trade_plan_audit.get("avg_price_deviation_pct", 0) or 0)
        if float(trade_plan_audit.get("match_rate", 0) or 0) < 0.85:
            adjusted["policy_exposure_multiplier"] = min(
                float(adjusted.get("policy_exposure_multiplier", 1.0) or 1.0),
                warn_exposure_multiplier,
            )
            adjusted["alerts"] = _merge_alerts(list(adjusted.get("alerts", []) or []), "trade_plan_drift")
        adjusted["policy_note"] = (
            f"{policy.note}; 计划命中率/plan match rate "
            f"{float(trade_plan_audit.get('match_rate', 0) or 0):.1%}"
        )

    if _alert_rank(policy.alert_level) > _alert_rank(str(adjusted.get("alert_level", "pass"))):
        adjusted["alert_level"] = policy.alert_level
    elif policy.state in {"recovered"}:
        adjusted["alert_level"] = "pass"

    if policy.action in {"pause", "reduce"}:
        adjusted["action"] = policy.action
    elif policy.state in {"recovered"} and str(adjusted.get("action", "")) == "pause":
        adjusted["action"] = "keep"

    adjusted["alerts"] = _merge_alerts(list(adjusted.get("alerts", []) or []), *policy.alerts)
    return adjusted


def _recent_strategy_records(
    records: list[dict[str, Any]],
    strategy: str,
    *,
    as_of: date | None,
    window_days: int,
) -> list[dict[str, Any]]:
    dated = _dated_strategy_records(records, strategy)
    if not dated:
        return []
    usable_dates = [item_date for _record, item_date in dated if item_date is not None]
    if not usable_dates:
        return []
    end = as_of or max(usable_dates)
    start = end - timedelta(days=max(window_days - 1, 0))
    return [
        record
        for record, item_date in dated
        if item_date is not None and start <= item_date <= end
    ]


def _dated_strategy_records(records: list[dict[str, Any]], strategy: str) -> list[tuple[dict[str, Any], date | None]]:
    return [
        (record, _record_date(record))
        for record in records
        if not strategy or str(record.get("strategy", "")).strip() == strategy
    ]


def _recovery_evidence(
    strategy_health: dict[str, Any] | None,
    *,
    match_rate_min: float,
    max_unmatched_plans: int,
    max_orphan_trades: int,
) -> dict[str, Any]:
    health = dict(strategy_health or {})
    reasons: list[str] = []
    ready = True

    trade_plan_audit = dict(health.get("trade_plan_audit") or {})
    if trade_plan_audit:
        match_rate = float(trade_plan_audit.get("match_rate", 0) or 0)
        unmatched_plans = int(trade_plan_audit.get("unmatched_plans", 0) or 0)
        orphan_trades = int(trade_plan_audit.get("orphan_trades", 0) or 0)
        if match_rate < match_rate_min:
            ready = False
            reasons.append(f"plan match {match_rate:.1%} < {match_rate_min:.1%}")
        else:
            reasons.append(f"plan match {match_rate:.1%}")
        if unmatched_plans > max_unmatched_plans:
            ready = False
            reasons.append(f"unmatched plans {unmatched_plans} > {max_unmatched_plans}")
        if orphan_trades > max_orphan_trades:
            ready = False
            reasons.append(f"orphan trades {orphan_trades} > {max_orphan_trades}")
    else:
        reasons.append("no trade-plan audit history")

    lifecycle_pressure = dict(health.get("lifecycle_pressure") or {})
    if lifecycle_pressure:
        doctor_status = str(lifecycle_pressure.get("doctor_status", "") or "")
        if doctor_status in {"warn", "fail"}:
            ready = False
            reasons.append(f"review doctor {doctor_status}")
        issue_names = {str(item) for item in lifecycle_pressure.get("doctor_issue_names", []) or []}
        blocking_issues = {
            "missing_execution_confirmations",
            "missing_lifecycle_snapshots",
            "missing_trading_day_states",
            "stale_lifecycle_snapshot",
            "stale_trading_day_state",
            "latest_lifecycle_blocked",
            "latest_trading_day_blocked",
            "latest_exit_sell_all",
        }
        still_open = sorted(issue_names & blocking_issues)
        if still_open:
            ready = False
            reasons.append("open doctor issues: " + ", ".join(still_open))
        latest_match_rate = lifecycle_pressure.get("latest_trade_plan_match_rate")
        if latest_match_rate not in (None, "") and float(latest_match_rate) >= match_rate_min:
            reasons.append(f"latest lifecycle match {float(latest_match_rate):.1%}")
    else:
        reasons.append("no review-memory pressure history")

    return {"ready": ready, "reasons": reasons}


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
