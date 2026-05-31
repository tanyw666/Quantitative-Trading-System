from quant_system.reports.execution_confirm import render_execution_confirmation_markdown
from quant_system.risk.execution_confirm import build_execution_confirmation


def test_render_execution_confirmation_markdown_includes_trade_ticket_fields():
    result = build_execution_confirmation(
        {
            "symbol": "000001",
            "status": "pass",
            "planned_pct": 0.1,
            "allowed_pct": 0.1,
            "planned_value": 10000,
            "allowed_value": 10000,
            "entry_price": 10.0,
            "stop_price": 9.5,
            "target_price": 11.5,
            "reward_risk": 3.0,
            "candidate_snapshot": {"name": "Demo", "close": 10.0},
            "checks": [],
        },
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

    content = render_execution_confirmation_markdown(result)

    assert "Status: pass" in content
    assert "Suggested quantity: 1000 shares" in content
    assert "Battle Plan Position" in content
    assert "Precheck Summary" in content
