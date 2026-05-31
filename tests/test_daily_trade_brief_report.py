from quant_system.reports.daily_trade_brief import build_daily_trade_brief, render_daily_trade_brief_markdown


def test_build_daily_trade_brief_rolls_up_gate_and_candidates():
    brief = build_daily_trade_brief(
        workflow_summary={"status": "warn"},
        battle_plan={
            "status": "warn",
            "target_exposure_pct": 0.3,
            "allocated_pct": 0.1,
            "must_do": [{"priority": "P0", "text": "reduce old position"}],
            "buy_candidates": [
                {
                    "symbol": "000001",
                    "name": "Demo",
                    "status": "warn",
                    "planned_pct": 0.05,
                    "allowed_pct": 0.03,
                    "entry_price": 10,
                    "stop_price": 9.5,
                    "target_price": 11.5,
                }
            ],
            "blocked_candidates": [{"symbol": "000002", "name": "Blocked", "reason": "gate blocked"}],
        },
        cockpit={"status": "warn", "action_items": [{"priority": "P1", "text": "check execution drift"}]},
        assistant={"status": "warn", "urgent_actions": [{"priority": "P0", "text": "clear approval warnings"}]},
        review_doctor={"status": "warn", "action_items": ["persist execution confirmations"]},
        review_attribution={"status": "warn", "action_items": ["review gate violations"]},
        attribution_policy={"status": "warn", "action_items": ["size down tomorrow"]},
        outputs={"summary": "reports/trading_day_workflow.json"},
        limit=10,
    )

    assert brief["status"] == "warn"
    assert brief["can_open_new_position"] is True
    assert brief["counts"]["allowed_orders"] == 1
    assert brief["counts"]["blocked_orders"] == 1
    assert any(item["text"] == "clear approval warnings" for item in brief["must_handle"])
    assert "review gate violations" in brief["review_actions"]


def test_render_daily_trade_brief_markdown_outputs_sections():
    content = render_daily_trade_brief_markdown(
        {
            "status": "block",
            "can_open_new_position": False,
            "decision": "禁止新增买入；先处理阻断。",
            "target_exposure_pct": 0.3,
            "allocated_pct": 0.1,
            "must_handle": [{"priority": "P0", "text": "sell weak holding"}],
            "allowed_orders": [],
            "blocked_orders": [{"symbol": "000002", "name": "Blocked", "reason": "approval block"}],
            "review_actions": ["run review attribution"],
            "next_commands": ["python -m quant_system review attribution --format markdown"],
        }
    )

    assert "# 今日交易主清单" in content
    assert "能否开新仓：不可以" in content
    assert "## 允许买入" in content
    assert "## 禁止或观察" in content
    assert "approval block" in content
