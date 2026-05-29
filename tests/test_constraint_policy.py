from quant_system.risk.constraint_policy import apply_constraint_policy_to_health, build_strategy_constraint_policy


def test_build_strategy_constraint_policy_enters_cooldown_after_repeated_blocks():
    policy = build_strategy_constraint_policy(
        {"strategy": "dragon", "alert_level": "pass", "action": "increase", "alerts": []},
        [
            {"created_at": "2026-05-28T09:00:00+00:00", "strategy": "dragon", "alert_level": "block", "alerts": ["mistake_cluster"]},
            {"created_at": "2026-05-29T09:10:00+00:00", "strategy": "dragon", "alert_level": "block", "alerts": ["execution_deviation"]},
        ],
    )

    assert policy.state == "cooldown"
    assert policy.action == "pause"
    assert policy.alert_level == "block"
    assert policy.exposure_multiplier == 0.0
    assert "冷静期" in policy.note


def test_apply_constraint_policy_to_health_overrides_base_action():
    adjusted = apply_constraint_policy_to_health(
        {"strategy": "trend", "alert_level": "pass", "action": "increase", "alerts": [], "score": 82},
        [{"created_at": "2026-05-29T09:10:00+00:00", "strategy": "trend", "alert_level": "warn", "alerts": ["execution_deviation"]}],
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
        warn_escalation_count=3,
        warn_exposure_multiplier=0.3,
        recover_after_clean_days=4,
    )

    assert policy.state == "watch"
    assert policy.exposure_multiplier == 0.3
    assert "连续4日" in policy.note
