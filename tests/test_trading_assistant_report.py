from quant_system.reports.trading_assistant import build_trading_assistant, render_trading_assistant_markdown


def test_build_trading_assistant_rolls_up_components():
    report = build_trading_assistant(
        context={
            "market_temperature": {"regime": "warm", "stance": "test"},
            "allocation_plan": {"target_exposure_pct": 0.3, "allocated_pct": 0.1},
            "final_battle_plan": {
                "status": "warn",
                "decision": "reduce",
                "must_do": [{"priority": "P0", "text": "clear warn"}],
                "buy_candidates": [
                    {
                        "symbol": "000001",
                        "name": "Demo",
                        "status": "warn",
                        "planned_pct": 0.05,
                        "allowed_pct": 0.04,
                        "entry_price": 10,
                        "stop_price": 9.5,
                    }
                ],
                "blocked_candidates": [{"symbol": "000002", "name": "Blocked", "reason": "gate blocked"}],
            },
            "approval_cooldown": {
                "status": "warn",
                "constraint_count": 1,
                "by_alert_level": {"warn": 1},
                "action_items": ["slow down dragon"],
            },
        },
        cockpit={
            "status": "warn",
            "decision": "reduce",
            "action_items": [{"priority": "P1", "text": "review cockpit"}],
            "execution_audit": {"warn": 1},
            "gate_review": {"violations": 1},
            "position_control": {"lifecycle": "warn"},
        },
        timeline={"status": "warn", "action_items": ["finish timeline"], "phases": [{"phase": "intraday", "status": "warn"}]},
        watchdog={"status": "block", "action_items": ["refresh workflow"], "alerts": [{"name": "stale_state"}], "phase_issue_counts": {"intraday": 2}},
        state={"status": "warn", "date": "2026-05-30", "phase_count": 4},
        limit=10,
    )

    assert report["status"] == "block"
    assert report["cards"]["approval_cooldown"]["warn"] == 1
    assert report["cards"]["watchdog"]["alerts"] == 1
    assert len(report["urgent_actions"]) >= 3
    assert report["buy_candidates"][0]["symbol"] == "000001"


def test_render_trading_assistant_markdown_outputs_sections():
    content = render_trading_assistant_markdown(
        {
            "status": "warn",
            "decision": "reduced-size only",
            "cards": {
                "market": {"regime": "warm"},
                "battle_plan": {"status": "warn"},
                "approval_cooldown": {"status": "warn"},
                "cockpit": {"status": "warn"},
                "timeline": {"status": "warn"},
                "watchdog": {"status": "pass"},
            },
            "urgent_actions": [{"priority": "P0", "text": "clear warns"}],
            "buy_candidates": [
                {
                    "symbol": "000001",
                    "name": "Demo",
                    "status": "warn",
                    "planned_pct": 0.05,
                    "allowed_pct": 0.04,
                    "entry_price": 10,
                    "stop_price": 9.5,
                }
            ],
            "blocked_candidates": [{"symbol": "000002", "name": "Blocked", "reason": "gate blocked"}],
        }
    )

    assert "# 交易助手" in content
    assert "## 优先动作" in content
    assert "## 审批冷静期" in content
    assert "## 可执行候选" in content
    assert "阻断候选" in content
