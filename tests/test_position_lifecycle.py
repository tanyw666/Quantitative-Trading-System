from argparse import Namespace
import json

import quant_system.cli as cli
from quant_system.reports.position_lifecycle import build_position_lifecycle_snapshot, render_position_lifecycle_lines


def test_build_position_lifecycle_snapshot_rolls_up_block_status():
    snapshot = build_position_lifecycle_snapshot(
        trade_plan_summary={"total": 2, "planned_value": 2000, "allowed_value": 1800, "warn_count": 1},
        lot_book={"total_open_lots": 1, "open_unrealized_pnl": 100, "summary": {"stale_open_lot_count": 1}},
        holding_action_plan={"status": "warn", "exit_count": 0, "reduce_count": 1, "watch_count": 1},
        exit_plan={"status": "block", "sell_all_count": 1, "take_profit_count": 0, "time_stop_count": 0},
        trade_plan_audit={"total_plans": 2, "match_rate": 0.5},
        action_execution_summary={"actionable_count": 1, "execution_rate": 1.0, "missed_count": 0},
        exit_execution_summary={"actionable_count": 1, "execution_rate": 0.0, "missed_count": 1},
        lot_exit_execution_summary={"actionable_count": 1, "execution_rate": 0.0, "missed_count": 1},
    )

    assert snapshot["status"] == "block"
    assert snapshot["exit_plan"]["sell_all_count"] == 1
    assert snapshot["execution"]["lot_exit_execution_rate"] == 0.0


def test_render_position_lifecycle_lines_shows_summary_and_actions():
    snapshot = build_position_lifecycle_snapshot(
        trade_plan_summary={"total": 1, "planned_value": 1000, "allowed_value": 1000, "warn_count": 0},
        lot_book={"total_open_lots": 1, "open_unrealized_pnl": 50, "summary": {"stale_open_lot_count": 0}},
        holding_action_plan={"status": "pass", "exit_count": 0, "reduce_count": 0, "watch_count": 0},
        exit_plan={"status": "pass", "sell_all_count": 0, "take_profit_count": 1, "time_stop_count": 0},
        trade_plan_audit={"total_plans": 1, "match_rate": 1.0},
        action_execution_summary={"actionable_count": 0, "execution_rate": 0.0, "missed_count": 0},
        exit_execution_summary={"actionable_count": 1, "execution_rate": 1.0, "missed_count": 0},
        lot_exit_execution_summary={"actionable_count": 1, "execution_rate": 1.0, "missed_count": 0},
    )

    lines = render_position_lifecycle_lines(snapshot)

    assert any("Buy plan:" in line for line in lines)
    assert any("Execution:" in line for line in lines)
    assert any("Action items:" in line for line in lines)


def test_portfolio_lifecycle_cli_outputs_snapshot(tmp_path, capsys):
    journal = tmp_path / "trades.jsonl"
    plan_log = tmp_path / "trade_plans.jsonl"
    action_log = tmp_path / "position_actions.jsonl"
    exit_log = tmp_path / "exit_plans.jsonl"
    journal.write_text(
        json.dumps({"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100}) + "\n",
        encoding="utf-8",
    )
    plan_log.write_text(
        json.dumps({"trade_date": "2026-05-29", "symbol": "000001", "planned_value": 1000, "allowed_value": 1000, "status": "pass", "gate_status": "pass"}) + "\n",
        encoding="utf-8",
    )
    action_log.write_text(
        json.dumps({"action_date": "2026-05-29", "status": "warn", "exit_count": 0, "reduce_count": 1, "watch_count": 0, "actions": []}) + "\n",
        encoding="utf-8",
    )
    exit_log.write_text(
        json.dumps({"plan_date": "2026-05-29", "status": "warn", "sell_all_count": 0, "take_profit_count": 1, "time_stop_count": 0, "items": []}) + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal,
        sqlite=None,
        price=["000001=11"],
        action_log=action_log,
        exit_log=exit_log,
        trade_plan_log=plan_log,
        as_of="2026-05-29",
        lookahead_days=3,
        limit=20,
        format="json",
        output=None,
        plan_log=None,
        log=None,
        trade_log=None,
    )

    cli.run_portfolio_lifecycle(args)

    output = capsys.readouterr().out
    assert '"trade_plan"' in output
    assert '"lots"' in output
    assert '"execution"' in output


def test_review_lifecycle_cli_outputs_markdown(tmp_path, capsys):
    journal = tmp_path / "trades.jsonl"
    journal.write_text(
        json.dumps({"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100}) + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal,
        sqlite=None,
        price=["000001=11"],
        action_log=tmp_path / "position_actions.jsonl",
        exit_log=tmp_path / "exit_plans.jsonl",
        trade_plan_log=tmp_path / "trade_plans.jsonl",
        as_of="2026-05-29",
        lookahead_days=3,
        limit=20,
        format="markdown",
        output=None,
        plan_log=None,
        log=None,
        trade_log=None,
    )

    cli.run_review_lifecycle(args)

    output = capsys.readouterr().out
    assert "Position Lifecycle" in output
    assert "Buy plan:" in output
