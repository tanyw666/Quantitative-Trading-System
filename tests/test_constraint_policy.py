from datetime import date

from quant_system.risk.constraint_policy import apply_constraint_policy_to_health, build_strategy_constraint_policy


def test_build_strategy_constraint_policy_enters_cooldown_after_repeated_blocks():
    policy = build_strategy_constraint_policy(
        {"strategy": "dragon", "alert_level": "pass", "action": "increase", "alerts": []},
        [
            {"created_at": "2026-05-28T09:00:00+00:00", "strategy": "dragon", "alert_level": "block", "alerts": ["mistake_cluster"]},
            {"created_at": "2026-05-29T09:10:00+00:00", "strategy": "dragon", "alert_level": "block", "alerts": ["execution_deviation"]},
        ],
        as_of=date(2026, 5, 29),
    )

    assert policy.state == "cooldown"
    assert policy.action == "pause"
    assert policy.alert_level == "block"
    assert policy.exposure_multiplier == 0.0
    assert "pause new BUY" in policy.note


def test_apply_constraint_policy_to_health_overrides_base_action():
    adjusted = apply_constraint_policy_to_health(
        {"strategy": "trend", "alert_level": "pass", "action": "increase", "alerts": [], "score": 82},
        [{"created_at": "2026-05-29T09:10:00+00:00", "strategy": "trend", "alert_level": "warn", "alerts": ["execution_deviation"]}],
        as_of=date(2026, 5, 29),
    )

    assert adjusted["action"] == "reduce"
    assert adjusted["alert_level"] == "warn"
    assert adjusted["constraint_policy"]["state"] == "watch"
    assert "execution_deviation" in adjusted["alerts"]


def test_constraint_policy_respects_custom_thresholds():
    policy = build_strategy_constraint_policy(
        {"strategy": "dragon", "alert_level": "pass", "action": "keep", "alerts": []},
        [
            {"created_at": "2026-05-28T09:00:00+00:00", "strategy": "dragon", "alert_level": "warn", "alerts": ["execution_deviation"]},
            {"created_at": "2026-05-29T09:00:00+00:00", "strategy": "dragon", "alert_level": "warn", "alerts": ["mistake_cluster"]},
        ],
        as_of=date(2026, 5, 29),
        warn_escalation_count=3,
        warn_exposure_multiplier=0.3,
        recover_after_clean_days=4,
    )

    assert policy.state == "watch"
    assert policy.exposure_multiplier == 0.3
    assert "warning watch" in policy.note


def test_constraint_policy_enters_recovery_probe_after_clean_days():
    policy = build_strategy_constraint_policy(
        _clean_health(),
        [
            {"created_at": "2026-05-26T09:00:00+00:00", "strategy": "dragon", "alert_level": "block", "alerts": ["mistake_cluster"]},
        ],
        as_of=date(2026, 5, 29),
        recover_after_clean_days=3,
        recover_probe_days=2,
        recover_probe_exposure_multiplier=0.25,
    )

    assert policy.state == "recovery_probe"
    assert policy.action == "reduce"
    assert policy.alert_level == "warn"
    assert policy.exposure_multiplier == 0.25
    assert policy.clean_days == 3
    assert policy.recovery_ready is True


def test_constraint_policy_recovers_after_probe_days():
    adjusted = apply_constraint_policy_to_health(
        {
            **_clean_health(),
            "alert_level": "block",
            "action": "pause",
            "alerts": ["mistake_cluster"],
        },
        [
            {"created_at": "2026-05-25T09:00:00+00:00", "strategy": "dragon", "alert_level": "block", "alerts": ["mistake_cluster"]},
        ],
        as_of=date(2026, 5, 30),
        recover_after_clean_days=3,
        recover_probe_days=2,
    )

    assert adjusted["policy_state"] == "recovered"
    assert adjusted["alert_level"] == "pass"
    assert adjusted["action"] == "keep"
    assert adjusted["policy_exposure_multiplier"] == 1.0
    assert adjusted["policy_recovery_ready"] is True


def test_constraint_policy_keeps_block_when_recovery_evidence_is_dirty():
    policy = build_strategy_constraint_policy(
        {
            "strategy": "dragon",
            "alert_level": "pass",
            "action": "keep",
            "alerts": [],
            "trade_plan_audit": {"match_rate": 0.6, "unmatched_plans": 2, "orphan_trades": 1},
            "lifecycle_pressure": {"doctor_status": "warn", "doctor_issue_names": ["missing_execution_confirmations"]},
        },
        [
            {"created_at": "2026-05-26T09:00:00+00:00", "strategy": "dragon", "alert_level": "block", "alerts": ["mistake_cluster"]},
        ],
        as_of=date(2026, 5, 30),
        recover_after_clean_days=3,
    )

    assert policy.state == "blocked"
    assert policy.recovery_ready is False
    assert any("plan match" in item for item in policy.recovery_reasons)
    assert any("review doctor" in item for item in policy.recovery_reasons)


def _clean_health():
    return {
        "strategy": "dragon",
        "alert_level": "pass",
        "action": "keep",
        "alerts": [],
        "trade_plan_audit": {"match_rate": 1.0, "unmatched_plans": 0, "orphan_trades": 0},
        "lifecycle_pressure": {"doctor_status": "pass", "doctor_issue_names": []},
    }
