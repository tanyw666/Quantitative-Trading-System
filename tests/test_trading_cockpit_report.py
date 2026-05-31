from quant_system.reports.trading_cockpit import build_trading_cockpit, render_trading_cockpit_markdown


def test_build_trading_cockpit_blocks_on_execution_approval_and_final_gate_pressure():
    cockpit = build_trading_cockpit(
        {
            "market_temperature": {"regime": "warm", "stance": "test"},
            "allocation_plan": {"target_exposure_pct": 0.3, "allocated_pct": 0.1},
            "final_battle_plan": {
                "status": "block",
                "decision": "do not buy",
                "must_do": [{"priority": "P0", "text": "clear blocks"}],
                "buy_candidates": [],
                "blocked_candidates": [],
            },
            "approval_cooldown": {"status": "block", "constraint_count": 1, "by_alert_level": {"block": 1}, "action_items": ["pause dragon"]},
            "holding_risk": {"status": "pass"},
            "holding_action_plan": {"status": "warn", "actions": [{"symbol": "000001", "action": "exit", "reason": "stop"}]},
            "exit_plan": {"status": "warn", "items": [{"symbol": "000002", "action": "sell_all", "plan_type": "invalidated"}]},
            "lifecycle_snapshot": {"status": "block"},
        },
        execution_audit={"block_count": 1, "warn_count": 0, "action_items": ["fix confirmation violations"]},
        trade_plan_audit={"total_plans": 2, "match_rate": 0.5, "action_items": ["bind every buy to plan"]},
        gate_review={"violation_count": 1, "buy_status_counts": {"block": 1}, "action_items": ["review blocked buy"]},
        execution_confirmations=[{"status": "block"}],
    )

    assert cockpit["status"] == "block"
    assert cockpit["approval_cooldown"]["block"] == 1
    assert any("pause dragon" in item["text"] for item in cockpit["action_items"])
    assert cockpit["execution_audit"]["block"] == 1


def test_render_trading_cockpit_markdown_outputs_unified_sections():
    cockpit = {
        "status": "warn",
        "decision": "reduce only",
        "reasons": ["execution drift"],
        "market": {"regime": "warm"},
        "final_battle_plan": {"status": "warn"},
        "approval_cooldown": {"status": "warn", "constraint_count": 1},
        "execution_audit": {"warn": 1},
        "trade_plan_audit": {"plans": 2},
        "gate_review": {"violations": 1},
        "position_control": {"holding_risk": "warn"},
        "confirmations": {"total": 1},
        "candidates": {"records": [{"symbol": "000001", "name": "Demo", "status": "warn", "planned_pct": 0.05, "allowed_pct": 0.06}]},
        "action_items": [{"priority": "P0", "text": "handle drift"}],
    }

    content = render_trading_cockpit_markdown(cockpit)

    assert "# 交易驾驶舱" in content
    assert "优先动作" in content
    assert "审批冷静期" in content
    assert "执行审计" in content
    assert "000001 Demo" in content
