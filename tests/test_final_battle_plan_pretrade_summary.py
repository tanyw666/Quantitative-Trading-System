from quant_system.reports.final_battle_plan import build_final_battle_plan, render_final_battle_plan_lines


def test_final_battle_plan_keeps_pretrade_summary_for_allowed_candidate():
    plan = build_final_battle_plan(
        {
            "market_temperature": {"regime": "warm", "stance": "test"},
            "allocation_plan": {
                "target_exposure_pct": 0.2,
                "allocated_pct": 0.1,
                "strategy_action": "keep",
                "strategy_alert_level": "pass",
                "items": [{"symbol": "000001"}],
            },
            "holding_risk": {"status": "pass"},
            "holding_action_plan": {"status": "pass"},
            "exit_plan": {"status": "pass"},
            "pretrade_checks": [
                {
                    "symbol": "000001",
                    "status": "warn",
                    "planned_pct": 0.05,
                    "allowed_pct": 0.05,
                    "entry_price": 10,
                    "candidate_snapshot": {"name": "Demo", "reason": "clean breakout"},
                    "checks": [
                        {"status": "warn", "message": "Quiet pullback; buy near support."},
                        {"status": "pass", "message": "ok"},
                    ],
                },
            ],
        }
    )

    assert plan["buy_candidates"][0]["pretrade_summary"] == ["[warn] Quiet pullback; buy near support."]

    content = "\n".join(render_final_battle_plan_lines(plan))
    assert "[warn] Quiet pullback; buy near support." in content


def test_final_battle_plan_keeps_pretrade_summary_for_blocked_candidate():
    plan = build_final_battle_plan(
        {
            "market_temperature": {"regime": "warm", "stance": "test"},
            "allocation_plan": {
                "target_exposure_pct": 0.2,
                "allocated_pct": 0.1,
                "strategy_action": "keep",
                "strategy_alert_level": "pass",
                "items": [{"symbol": "000002"}],
            },
            "holding_risk": {"status": "pass"},
            "holding_action_plan": {"status": "pass"},
            "exit_plan": {"status": "pass"},
            "pretrade_checks": [
                {
                    "symbol": "000002",
                    "status": "block",
                    "planned_pct": 0.05,
                    "allowed_pct": 0.05,
                    "entry_price": 12,
                    "candidate_snapshot": {"name": "Blocked", "reason": "late breakout"},
                    "checks": [
                        {"status": "block", "message": "False-breakout flag is active."},
                    ],
                },
            ],
        }
    )

    assert plan["blocked_candidates"][0]["pretrade_summary"] == ["[block] False-breakout flag is active."]

    content = "\n".join(render_final_battle_plan_lines(plan))
    assert "[block] False-breakout flag is active." in content
