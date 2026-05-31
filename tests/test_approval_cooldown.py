from quant_system.risk.approval_cooldown import (
    build_approval_cooldown_constraints,
    render_approval_cooldown_markdown,
    summarize_approval_cooldown,
)


def test_approval_cooldown_pauses_on_block_violation():
    summary = {
        "records": [
            {
                "audit_type": "approval",
                "status": "block",
                "strategy": "dragon",
                "symbol": "000001",
                "approval_status": "block",
                "trade_status": "matched",
                "linked_by": "approval_id",
                "reasons": ["Approval status was block, but a BUY trade was still recorded."],
            }
        ]
    }

    constraints = build_approval_cooldown_constraints(summary, created_at="2026-05-30T10:00:00+00:00")

    assert len(constraints) == 1
    assert constraints[0]["strategy"] == "dragon"
    assert constraints[0]["alert_level"] == "block"
    assert constraints[0]["action"] == "pause"
    assert constraints[0]["exposure_multiplier"] == 0.0
    assert "block_approval_executed" in constraints[0]["alerts"]


def test_approval_cooldown_reduces_on_repeated_fallback_links():
    summary = {
        "records": [
            {
                "audit_type": "approval",
                "status": "warn",
                "strategy": "trend",
                "symbol": "000001",
                "approval_status": "pass",
                "trade_status": "matched",
                "linked_by": "fallback_symbol_date",
                "reasons": ["Trade was matched by symbol/date fallback instead of explicit approval id."],
            },
            {
                "audit_type": "approval",
                "status": "warn",
                "strategy": "trend",
                "symbol": "000002",
                "approval_status": "pass",
                "trade_status": "matched",
                "linked_by": "fallback_symbol_date",
                "reasons": ["Trade was matched by symbol/date fallback instead of explicit approval id."],
            },
        ]
    }

    constraints = build_approval_cooldown_constraints(summary, warn_threshold=3, fallback_threshold=2)
    payload = summarize_approval_cooldown(constraints)
    content = render_approval_cooldown_markdown(payload)

    assert constraints[0]["alert_level"] == "warn"
    assert constraints[0]["action"] == "reduce"
    assert constraints[0]["exposure_multiplier"] == 0.5
    assert "approval_fallback_link" in constraints[0]["alerts"]
    assert "# 审批冷静期" in content
