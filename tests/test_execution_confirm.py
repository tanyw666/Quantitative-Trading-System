from quant_system.risk.execution_confirm import build_execution_confirmation


def pretrade_payload(status: str = "pass") -> dict:
    return {
        "symbol": "000001",
        "status": status,
        "planned_pct": 0.1,
        "allowed_pct": 0.1,
        "planned_value": 10000,
        "allowed_value": 10000,
        "entry_price": 10.0,
        "stop_price": 9.5,
        "target_price": 11.5,
        "candidate_snapshot": {"name": "Demo", "close": 10.0},
        "checks": [],
    }


def test_execution_confirmation_passes_with_lot_size_and_reference_control():
    result = build_execution_confirmation(
        pretrade_payload(),
        battle_plan={
            "status": "pass",
            "decision": "ok",
            "buy_candidates": [{"symbol": "000001", "planned_pct": 0.1, "allowed_pct": 0.1, "entry_price": 10.0}],
            "blocked_candidates": [],
        },
        current_price=10.05,
        planned_pct=0.1,
        cash=100000,
    )

    assert result.status == "pass"
    assert result.confirmed_pct == 0.1
    assert result.suggested_quantity == 900
    assert result.confirmed_value == 9045.0


def test_execution_confirmation_warns_and_scales_down_on_small_chase():
    result = build_execution_confirmation(
        pretrade_payload(),
        battle_plan={
            "status": "pass",
            "decision": "ok",
            "buy_candidates": [{"symbol": "000001", "planned_pct": 0.1, "allowed_pct": 0.1, "entry_price": 10.0}],
            "blocked_candidates": [],
        },
        current_price=10.2,
        planned_pct=0.1,
        cash=100000,
        warn_scale=0.5,
        max_price_deviation_pct=0.015,
        hard_chase_pct=0.03,
    )

    assert result.status == "warn"
    assert result.confirmed_pct == 0.05
    assert result.suggested_quantity == 400
    assert any(check.name == "price_drift" and check.status == "warn" for check in result.checks)


def test_execution_confirmation_blocks_on_final_battle_plan():
    result = build_execution_confirmation(
        pretrade_payload(),
        battle_plan={
            "status": "block",
            "decision": "do not buy",
            "reasons": ["strategy gate blocks new positions"],
            "buy_candidates": [{"symbol": "000001", "planned_pct": 0.1, "allowed_pct": 0.1, "entry_price": 10.0}],
            "blocked_candidates": [],
        },
        current_price=10.0,
        planned_pct=0.1,
        cash=100000,
    )

    assert result.status == "block"
    assert result.suggested_quantity == 0
    assert any(check.name == "final_gate" and check.status == "block" for check in result.checks)


def test_execution_confirmation_blocks_when_price_runs_too_far():
    result = build_execution_confirmation(
        pretrade_payload(),
        battle_plan={
            "status": "pass",
            "decision": "ok",
            "buy_candidates": [{"symbol": "000001", "planned_pct": 0.1, "allowed_pct": 0.1, "entry_price": 10.0}],
            "blocked_candidates": [],
        },
        current_price=10.35,
        planned_pct=0.1,
        cash=100000,
        hard_chase_pct=0.03,
    )

    assert result.status == "block"
    assert any(check.name == "price_drift" and check.status == "block" for check in result.checks)


def test_execution_confirmation_carries_pretrade_structure_warnings():
    payload = pretrade_payload("warn")
    payload["checks"] = [
        {
            "name": "chase_risk",
            "status": "warn",
            "message": "Chase-risk score 52.0 is elevated.",
        }
    ]

    result = build_execution_confirmation(
        payload,
        battle_plan={
            "status": "pass",
            "decision": "ok",
            "buy_candidates": [{"symbol": "000001", "planned_pct": 0.1, "allowed_pct": 0.1, "entry_price": 10.0}],
            "blocked_candidates": [],
        },
        current_price=10.0,
        planned_pct=0.1,
        cash=100000,
    )

    assert result.status == "warn"
    assert any(check.name == "pretrade_structure" and check.status == "warn" for check in result.checks)
    assert any("Chase-risk score" in item for item in result.action_items)
