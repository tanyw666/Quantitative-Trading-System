from quant_system.portfolio.lifecycle_pressure import build_lifecycle_pressure


def test_build_lifecycle_pressure_blocks_on_missed_exit_and_sell_all():
    pressure = build_lifecycle_pressure(
        {
            "status": "block",
            "lots": {"stale_open_lots": 1},
            "holding_actions": {"exit_count": 1, "reduce_count": 1},
            "exit_plan": {"sell_all_count": 1},
            "execution": {
                "trade_plan_match_rate": 0.5,
                "action_actionable_count": 1,
                "action_execution_rate": 1.0,
                "action_missed_count": 0,
                "exit_actionable_count": 1,
                "exit_execution_rate": 0.0,
                "exit_missed_count": 1,
                "lot_exit_actionable_count": 1,
                "lot_exit_execution_rate": 0.0,
                "lot_exit_missed_count": 1,
            },
        }
    )

    assert pressure["alert_level"] == "block"
    assert pressure["action"] == "pause"
    assert "lifecycle_block" in pressure["alerts"]
    assert "exit_execution_gap" in pressure["alerts"]
    assert pressure["score"] < 100
