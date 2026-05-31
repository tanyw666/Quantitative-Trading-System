from quant_system.portfolio.lifecycle_pressure import build_lifecycle_pressure, build_review_memory_pressure


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


def test_build_review_memory_pressure_tracks_repeated_blocks_and_doctor_warnings():
    pressure = build_review_memory_pressure(
        lifecycle_snapshots=[
            {
                "snapshot_date": "2026-05-27",
                "status": "warn",
                "execution": {
                    "trade_plan_match_rate": 0.9,
                    "action_execution_rate": 1.0,
                    "exit_execution_rate": 1.0,
                    "lot_exit_execution_rate": 1.0,
                },
            },
            {
                "snapshot_date": "2026-05-28",
                "status": "block",
                "execution": {
                    "trade_plan_match_rate": 0.6,
                    "action_execution_rate": 1.0,
                    "exit_execution_rate": 0.5,
                    "lot_exit_execution_rate": 0.0,
                },
            },
            {
                "snapshot_date": "2026-05-29",
                "status": "block",
                "execution": {
                    "trade_plan_match_rate": 0.5,
                    "action_execution_rate": 0.0,
                    "exit_execution_rate": 0.0,
                    "lot_exit_execution_rate": 0.0,
                },
            },
        ],
        doctor_report={
            "status": "warn",
            "issues": [
                {"name": "stale_lifecycle_snapshot", "status": "warn"},
                {"name": "latest_exit_sell_all", "status": "warn"},
            ],
        },
        limit=5,
    )

    assert pressure["alert_level"] == "block"
    assert pressure["action"] == "pause"
    assert pressure["block_count"] == 2
    assert pressure["status_trend"] == "worsening"
    assert pressure["doctor_issue_count"] == 2
    assert "lifecycle_repeated_block" in pressure["alerts"]
    assert "review_doctor_warn" in pressure["alerts"]
    assert pressure["score"] < 70
