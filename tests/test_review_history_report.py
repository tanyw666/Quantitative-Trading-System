from quant_system.reports.review_history import build_review_history, render_review_history_markdown


def test_build_review_history_summarizes_review_ledger():
    summary = build_review_history(
        trade_plans=[{"trade_date": "2026-05-29", "status": "pass", "gate_status": "warn", "planned_value": 8000, "allowed_value": 5000}],
        trades=[{"date": "2026-05-29", "side": "BUY", "amount": 5000}],
        action_plans=[{"action_date": "2026-05-29", "status": "warn", "reduce_count": 1}],
        exit_plans=[{"plan_date": "2026-05-29", "status": "block", "sell_all_count": 1, "expected_cash_release": 1000}],
        lifecycle_snapshots=[
            {
                "snapshot_date": "2026-05-29",
                "status": "block",
                "execution": {
                    "trade_plan_match_rate": 1.0,
                    "action_execution_rate": 0.5,
                    "exit_execution_rate": 0.0,
                    "lot_exit_execution_rate": 0.0,
                },
            }
        ],
    )

    assert summary["counts"]["trade_plans"] == 1
    assert summary["trade_plan"]["gate_counts"]["warn"] == 1
    assert summary["exits"]["sell_all_count"] == 1
    assert summary["lifecycle"]["status_counts"]["block"] == 1
    assert any("sell-all" in item.lower() for item in summary["action_items"])


def test_render_review_history_markdown_outputs_sections():
    content = render_review_history_markdown(
        {
            "counts": {"trade_plans": 1, "trades": 1, "action_plans": 1, "exit_plans": 1, "lifecycle_snapshots": 1},
            "trade_plan": {"planned_value": 8000, "allowed_value": 5000, "status_counts": {"pass": 1}, "gate_counts": {"warn": 1}},
            "actions": {"status_counts": {"warn": 1}},
            "exits": {"status_counts": {"block": 1}, "sell_all_count": 1, "expected_cash_release": 1000},
            "lifecycle": {
                "status_counts": {"block": 1},
                "avg_trade_plan_match_rate": 1.0,
                "avg_action_execution_rate": 0.5,
                "avg_exit_execution_rate": 0.0,
                "avg_lot_exit_execution_rate": 0.0,
            },
            "action_items": ["Latest lifecycle snapshot is blocked; pause new positions until execution gaps are closed."],
        }
    )

    assert "# Review History" in content
    assert "## Coverage" in content
    assert "## Lifecycle" in content
