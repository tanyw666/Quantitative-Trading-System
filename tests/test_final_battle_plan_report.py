from quant_system.reports.final_battle_plan import build_final_battle_plan, render_final_battle_plan_lines


def test_build_final_battle_plan_blocks_on_review_memory_and_exit_tasks():
    plan = build_final_battle_plan(
        {
            "market_temperature": {"regime": "warm", "stance": "test"},
            "allocation_plan": {
                "target_exposure_pct": 0,
                "allocated_pct": 0,
                "strategy_action": "pause",
                "strategy_alert_level": "block",
                "strategy_adjustment_note": "blocked by memory",
            },
            "holding_risk": {"status": "pass"},
            "holding_action_plan": {
                "status": "warn",
                "exit_count": 1,
                "actions": [{"symbol": "000001", "action": "exit", "reason": "stop loss"}],
            },
            "exit_plan": {
                "status": "warn",
                "sell_all_count": 1,
                "items": [{"symbol": "000002", "action": "sell_all", "plan_type": "invalidated"}],
            },
            "strategy_health": [
                {
                    "strategy": "dragon",
                    "lifecycle_pressure": {
                        "alert_level": "block",
                        "action": "pause",
                        "summary": "window 5; lifecycle block 2, warn 1",
                        "doctor_status": "warn",
                        "doctor_issue_count": 2,
                    },
                }
            ],
            "pretrade_checks": [
                {
                    "symbol": "000003",
                    "status": "block",
                    "planned_pct": 0.1,
                    "allowed_pct": 0,
                    "entry_price": 10,
                    "candidate_snapshot": {"name": "Blocked"},
                    "checks": [{"status": "block", "message": "strategy blocked"}],
                }
            ],
            "lifecycle_snapshot": {"status": "block"},
        }
    )

    assert plan["status"] == "block"
    assert "禁止新增买入" in plan["decision"]
    assert plan["pretrade_counts"]["block"] == 1
    assert len(plan["must_do"]) >= 3
    assert plan["blocked_candidates"][0]["symbol"] == "000003"


def test_build_final_battle_plan_moves_candidates_to_blocked_when_global_gate_blocks():
    plan = build_final_battle_plan(
        {
            "market_temperature": {"regime": "warm", "stance": "test"},
            "allocation_plan": {
                "target_exposure_pct": 0,
                "allocated_pct": 0,
                "strategy_action": "pause",
                "strategy_alert_level": "block",
            },
            "holding_risk": {"status": "pass"},
            "holding_action_plan": {"status": "pass"},
            "exit_plan": {"status": "pass"},
            "pretrade_checks": [
                {
                    "symbol": "000001",
                    "status": "pass",
                    "planned_pct": 0.1,
                    "allowed_pct": 0.1,
                    "entry_price": 10,
                    "candidate_snapshot": {"name": "PassButGlobalBlocked"},
                    "checks": [{"status": "pass", "message": "ok"}],
                }
            ],
        }
    )

    assert plan["status"] == "block"
    assert plan["buy_candidates"] == []
    assert plan["blocked_candidates"][0]["symbol"] == "000001"
    assert "final gate blocked" in plan["blocked_candidates"][0]["reason"]


def test_render_final_battle_plan_lines_outputs_execution_sections():
    lines = render_final_battle_plan_lines(
        {
            "status": "warn",
            "decision": "只允许计划内确认单",
            "market_regime": "warm",
            "market_stance": "test",
            "target_exposure_pct": 0.3,
            "allocated_pct": 0.1,
            "review_memory": {"summary": "window 3", "doctor_status": "pass", "doctor_issue_count": 0},
            "must_do": [{"priority": "P0", "text": "handle exit"}],
            "buy_candidates": [
                {
                    "symbol": "000001",
                    "name": "Demo",
                    "status": "warn",
                    "planned_pct": 0.05,
                    "allowed_pct": 0.06,
                    "entry_price": 10,
                    "stop_price": 9,
                    "target_price": 12,
                }
            ],
            "blocked_candidates": [],
        }
    )
    content = "\n".join(lines)

    assert "最终门禁：warn" in content
    assert "先处理" in content
    assert "可执行候选" in content
    assert "000001 Demo" in content
