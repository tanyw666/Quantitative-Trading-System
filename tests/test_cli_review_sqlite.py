from argparse import Namespace
import json

import pandas as pd

import quant_system.cli as cli
from quant_system.storage.sqlite_store import SQLiteStore


def test_review_selections_cli_can_read_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    csv_path = tmp_path / "prices.csv"
    SQLiteStore(sqlite_path).insert_selections(
        [
            {
                "date": "2024-01-01",
                "strategy": "demo",
                "symbol": "000001",
                "name": "Demo",
                "close": 10,
                "reason": "测试",
                "entry_gate": "pass",
            }
        ]
    )
    pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=4),
            "symbol": ["000001"] * 4,
            "open": [10, 11, 12, 13],
            "high": [10, 11, 12, 13],
            "low": [10, 11, 12, 13],
            "close": [10, 11, 12, 13],
            "volume": [1000] * 4,
        }
    ).to_csv(csv_path, index=False)
    args = Namespace(tracker=tmp_path / "unused.jsonl", sqlite=sqlite_path, csv=csv_path, horizons="1,3")

    cli.run_review_selections(args)

    output = capsys.readouterr().out
    assert '"summary"' in output
    assert '"entry_gate": "pass"' in output


def test_review_trade_list_cli_can_read_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    SQLiteStore(sqlite_path).insert_trade(
        {
            "date": "2024-01-02",
            "symbol": "000001",
            "side": "BUY",
            "price": 10.5,
            "quantity": 100,
            "reason": "test",
            "tags": ["plan"],
        }
    )
    args = Namespace(journal=tmp_path / "unused.jsonl", sqlite=sqlite_path)

    cli.run_review_trade_list(args)

    output = capsys.readouterr().out
    assert '"symbol": "000001"' in output
    assert '"tags": [' in output


def test_review_trade_add_attaches_workflow_gate(tmp_path, capsys):
    summary_path = tmp_path / "premarket_workflow.json"
    summary_path.write_text(
        json.dumps(
            {
                "gate": {
                    "status": "warn",
                    "message": "只允许计划内确认单",
                    "reasons": ["交易前预检存在预警项"],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = Namespace(
        journal=tmp_path / "trades.jsonl",
        sqlite=None,
        date="2026-05-29",
        symbol="000001",
        side="BUY",
        price=10.5,
        quantity=100,
        reason="test",
        name="Demo",
        strategy="strong_stock_screen",
        market_regime="warm",
        planned_pct=0.1,
        actual_pct=0.1,
        planned_price=10.0,
        stop_price=9.5,
        target_price=12.0,
        tags="计划内",
        mistake_type="",
        review="",
        workflow_summary=summary_path,
        gate_status="",
        gate_message="",
        gate_reason=[],
        discipline_exception=True,
        exception_reason="approved exception",
    )

    cli.run_review_trade_add(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["gate_status"] == "warn"
    assert payload["gate_reasons"] == ["交易前预检存在预警项", "forced-gate-warn"]
    assert "gate-warn" in payload["tags"]
    assert payload["discipline_exception"] is True
    assert payload["exception_reason"] == "approved exception"
    assert "discipline-exception" in payload["tags"]


def test_review_trade_stats_cli_can_read_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_trade({"date": "2024-01-02", "symbol": "000001", "side": "BUY", "price": 10, "quantity": 100, "reason": "buy", "amount": 1000, "tags": ["plan"]})
    store.insert_trade({"date": "2024-01-03", "symbol": "000001", "side": "SELL", "price": 11, "quantity": 100, "reason": "sell", "amount": 1100, "tags": ["exit"]})
    args = Namespace(journal=tmp_path / "unused.jsonl", sqlite=sqlite_path)

    cli.run_review_trade_stats(args)

    output = capsys.readouterr().out
    assert '"total_trades": 2' in output
    assert '"buy_count": 1' in output
    assert '"sell_count": 1' in output


def test_review_trade_plan_cli_reads_trade_plan_table_instead_of_trades(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_trade(
        {
            "date": "2026-05-29",
            "symbol": "000001",
            "side": "BUY",
            "price": 10,
            "quantity": 100,
            "reason": "trade-only",
            "amount": 1000,
        }
    )
    store.insert_trade_plan(
        {
            "created_at": "2026-05-29T09:00:00+00:00",
            "trade_date": "2026-05-29",
            "symbol": "000002",
            "name": "PlanOnly",
            "strategy": "dragon",
            "status": "pass",
            "gate_status": "warn",
            "planned_pct": 0.08,
            "planned_value": 8000,
            "allowed_pct": 0.05,
            "allowed_value": 5000,
            "entry_price": 10.2,
        }
    )
    args = Namespace(log=tmp_path / "unused.jsonl", sqlite=sqlite_path, limit=10, format="json", output=None)

    cli.run_review_trade_plan(args)

    output = capsys.readouterr().out
    assert '"total": 1' in output
    assert '"symbol": "000002"' in output
    assert '"planned_value": 8000.0' in output


def test_review_action_and_exit_audits_can_read_sqlite_records(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_trade(
        {
            "date": "2026-05-29",
            "symbol": "000001",
            "side": "SELL",
            "price": 9,
            "quantity": 100,
            "reason": "stop",
            "amount": 900,
        }
    )
    store.insert_position_action_plan(
        {
            "created_at": "2026-05-29T09:00:00+00:00",
            "action_date": "2026-05-29",
            "status": "warn",
            "actions": [
                {
                    "symbol": "000001",
                    "name": "Demo",
                    "action": "exit",
                    "current_quantity": 100,
                    "target_quantity": 0,
                    "quantity_delta": -100,
                    "market_price": 9.1,
                    "reason": "stop",
                }
            ],
        }
    )
    store.insert_exit_plan(
        {
            "created_at": "2026-05-29T10:00:00+00:00",
            "plan_date": "2026-05-29",
            "status": "block",
            "items": [
                {
                    "symbol": "000001",
                    "plan_type": "stop_loss",
                    "action": "sell_all",
                    "sell_quantity": 100,
                    "market_price": 9.1,
                }
            ],
        }
    )

    cli.run_review_action_execution(
        Namespace(
            action_log=tmp_path / "unused_actions.jsonl",
            trade_log=tmp_path / "unused_trades.jsonl",
            sqlite=sqlite_path,
            lookahead_days=3,
            limit=20,
            format="json",
            output=None,
        )
    )
    action_output = capsys.readouterr().out
    assert '"executed_count": 1' in action_output

    cli.run_review_exit_audit(
        Namespace(
            exit_log=tmp_path / "unused_exit.jsonl",
            trade_log=tmp_path / "unused_trades.jsonl",
            sqlite=sqlite_path,
            lookahead_days=3,
            limit=20,
            format="json",
            output=None,
        )
    )
    exit_output = capsys.readouterr().out
    assert '"executed_count": 1' in exit_output


def test_portfolio_lifecycle_can_persist_snapshot_to_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_trade(
        {
            "date": "2026-05-01",
            "symbol": "000001",
            "name": "Demo",
            "side": "BUY",
            "price": 10,
            "quantity": 100,
            "reason": "buy",
            "amount": 1000,
        }
    )
    store.insert_trade_plan(
        {
            "created_at": "2026-05-29T09:00:00+00:00",
            "trade_date": "2026-05-29",
            "symbol": "000001",
            "name": "Demo",
            "strategy": "dragon",
            "status": "pass",
            "gate_status": "pass",
            "planned_value": 1000,
            "allowed_value": 1000,
            "entry_price": 10,
        }
    )
    store.insert_position_action_plan(
        {
            "created_at": "2026-05-29T10:00:00+00:00",
            "action_date": "2026-05-29",
            "status": "warn",
            "exit_count": 0,
            "reduce_count": 1,
            "watch_count": 0,
            "actions": [],
        }
    )
    store.insert_exit_plan(
        {
            "created_at": "2026-05-29T11:00:00+00:00",
            "plan_date": "2026-05-29",
            "status": "warn",
            "sell_all_count": 0,
            "take_profit_count": 1,
            "time_stop_count": 0,
            "items": [],
        }
    )
    args = Namespace(
        journal=tmp_path / "unused_trades.jsonl",
        sqlite=sqlite_path,
        price=["000001=11"],
        action_log=tmp_path / "unused_actions.jsonl",
        exit_log=tmp_path / "unused_exit.jsonl",
        trade_plan_log=tmp_path / "unused_plan.jsonl",
        as_of="2026-05-29",
        lookahead_days=3,
        limit=20,
        format="json",
        output=None,
        record=True,
        plan_log=None,
        log=None,
        trade_log=None,
    )

    cli.run_portfolio_lifecycle(args)

    output = capsys.readouterr().out
    snapshots = store.read_lifecycle_snapshots()
    assert '"trade_plan"' in output
    assert len(snapshots) == 1
    assert snapshots.loc[0, "snapshot_date"] == "2026-05-29"


def test_data_db_import_review_migrates_jsonl_logs_without_duplicates(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    tracker = tmp_path / "selections.jsonl"
    journal = tmp_path / "trades.jsonl"
    trade_plan_log = tmp_path / "trade_plans.jsonl"
    confirm_log = tmp_path / "execution_confirms.jsonl"
    action_log = tmp_path / "actions.jsonl"
    exit_log = tmp_path / "exit_plans.jsonl"
    lifecycle_log = tmp_path / "lifecycle.jsonl"
    state_log = tmp_path / "states.jsonl"
    tracker.write_text('{"date":"2026-05-29","strategy":"dragon","symbol":"000001","name":"Demo","close":10,"reason":"watch"}\n', encoding="utf-8")
    journal.write_text('{"date":"2026-05-29","symbol":"000001","side":"BUY","price":10,"quantity":100,"reason":"buy","amount":1000}\n', encoding="utf-8")
    trade_plan_log.write_text('{"created_at":"2026-05-29T09:00:00+00:00","trade_date":"2026-05-29","symbol":"000001","strategy":"dragon","status":"pass","gate_status":"pass","planned_value":1000,"allowed_value":1000,"entry_price":10}\n', encoding="utf-8")
    confirm_log.write_text('{"created_at":"2026-05-29T09:30:00+00:00","symbol":"000001","status":"pass","current_price":10,"confirmed_value":1000,"suggested_quantity":100}\n', encoding="utf-8")
    action_log.write_text('{"created_at":"2026-05-29T10:00:00+00:00","action_date":"2026-05-29","status":"warn","actions":[]}\n', encoding="utf-8")
    exit_log.write_text('{"created_at":"2026-05-29T11:00:00+00:00","plan_date":"2026-05-29","status":"warn","items":[]}\n', encoding="utf-8")
    lifecycle_log.write_text('{"created_at":"2026-05-29T12:00:00+00:00","snapshot_date":"2026-05-29","status":"warn","execution":{"trade_plan_match_rate":1.0}}\n', encoding="utf-8")
    state_log.write_text('{"created_at":"2026-05-29T15:30:00+08:00","date":"2026-05-29","source":"workflow.trading-day","status":"warn","phase_count":4,"pass_count":3,"warn_count":1,"block_count":0,"action_item_count":1,"phases":[],"action_items":["demo"]}\n', encoding="utf-8")
    args = Namespace(
        db_path=sqlite_path,
        tracker=tracker,
        journal=journal,
        promotion_log=tmp_path / "promotions.jsonl",
        constraint_log=tmp_path / "constraints.jsonl",
        discipline_log=tmp_path / "discipline.jsonl",
        trade_plan_log=trade_plan_log,
        confirm_log=confirm_log,
        action_log=action_log,
        exit_log=exit_log,
        lifecycle_log=lifecycle_log,
        state_log=state_log,
    )

    cli.run_data_db_import_review(args)
    first_output = capsys.readouterr().out
    cli.run_data_db_import_review(args)
    second_output = capsys.readouterr().out

    store = SQLiteStore(sqlite_path)
    assert '"imported": 1' in first_output
    assert '"skipped": 1' in second_output
    assert len(store.read_selections()) == 1
    assert len(store.read_trade_plans()) == 1
    assert len(store.read_execution_confirmations()) == 1
    assert len(store.read_position_action_plans()) == 1
    assert len(store.read_exit_plans()) == 1
    assert len(store.read_lifecycle_snapshots()) == 1
    assert len(store.read_trading_day_states()) == 1


def test_review_timeline_history_can_read_jsonl_and_sqlite(tmp_path, capsys):
    state_log = tmp_path / "states.jsonl"
    state_log.write_text(
        '{"created_at":"2026-05-30T15:30:00+08:00","date":"2026-05-30","source":"workflow.trading-day","status":"block","phase_count":4,"pass_count":3,"warn_count":0,"block_count":1,"action_item_count":1,"phases":[{"phase":"post_trade","status":"block"}],"action_items":["补成交回写"]}\n',
        encoding="utf-8",
    )
    cli.run_review_timeline_history(
        Namespace(
            state_log=state_log,
            sqlite=None,
            limit=10,
            format="json",
            output=None,
        )
    )
    json_output = capsys.readouterr().out
    assert '"total_records": 1' in json_output
    assert '"post_trade": 1' in json_output

    sqlite_path = tmp_path / "quant.sqlite"
    SQLiteStore(sqlite_path).insert_trading_day_state(
        {
            "created_at": "2026-05-30T15:30:00+08:00",
            "date": "2026-05-30",
            "source": "workflow.trading-day",
            "status": "warn",
            "phase_count": 4,
            "pass_count": 3,
            "warn_count": 1,
            "block_count": 0,
            "action_item_count": 1,
            "phases": [{"phase": "intraday", "status": "warn"}],
            "action_items": ["检查确认单"],
        }
    )
    cli.run_review_timeline_history(
        Namespace(
            state_log=tmp_path / "unused.jsonl",
            sqlite=sqlite_path,
            limit=10,
            format="markdown",
            output=None,
        )
    )
    markdown_output = capsys.readouterr().out
    assert "Trading Day State History" in markdown_output
    assert "intraday" in markdown_output


def test_review_execution_audit_cli_can_read_confirmation_from_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_execution_confirmation(
        {
            "created_at": "2026-05-30T09:30:00+08:00",
            "symbol": "000001",
            "status": "pass",
            "current_price": 10,
            "confirmed_value": 1000,
            "suggested_quantity": 100,
        }
    )
    store.insert_trade(
        {
            "date": "2026-05-30",
            "symbol": "000001",
            "side": "BUY",
            "price": 10,
            "quantity": 100,
            "amount": 1000,
            "execution_confirmation_created_at": "2026-05-30T09:30:00+08:00",
            "review": "ok",
        }
    )

    cli.run_review_execution_audit(
        Namespace(
            confirm_log=tmp_path / "unused_confirms.jsonl",
            trade_log=tmp_path / "unused_trades.jsonl",
            journal=tmp_path / "unused_trades.jsonl",
            sqlite=sqlite_path,
            lookahead_days=1,
            limit=10,
            format="json",
            output=None,
        )
    )

    output = capsys.readouterr().out
    assert '"matched_trade_count": 1' in output
    assert '"block_count": 0' in output


def test_review_timeline_watch_can_read_jsonl_and_sqlite(tmp_path, capsys):
    state_log = tmp_path / "states.jsonl"
    state_log.write_text(
        '{"created_at":"2026-05-28T15:30:00+08:00","date":"2026-05-28","source":"workflow.trading-day","status":"warn","phase_count":4,"pass_count":3,"warn_count":1,"block_count":0,"action_item_count":1,"phases":[{"phase":"intraday","status":"warn"}],"action_items":["检查确认单"]}\n'
        '{"created_at":"2026-05-29T15:30:00+08:00","date":"2026-05-29","source":"workflow.trading-day","status":"block","phase_count":4,"pass_count":2,"warn_count":1,"block_count":1,"action_item_count":1,"phases":[{"phase":"intraday","status":"block"}],"action_items":["停止新开仓"]}\n',
        encoding="utf-8",
    )
    cli.run_review_timeline_watch(
        Namespace(
            state_log=state_log,
            sqlite=None,
            as_of="2026-05-30",
            repeat_threshold=2,
            stale_days=0,
            limit=10,
            format="json",
            output=None,
        )
    )
    json_output = capsys.readouterr().out
    assert '"status": "block"' in json_output
    assert '"repeated_phase_issue"' in json_output

    sqlite_path = tmp_path / "quant.sqlite"
    SQLiteStore(sqlite_path).insert_trading_day_state(
        {
            "created_at": "2026-05-30T15:30:00+08:00",
            "date": "2026-05-30",
            "source": "workflow.trading-day",
            "status": "warn",
            "phase_count": 4,
            "pass_count": 3,
            "warn_count": 1,
            "block_count": 0,
            "action_item_count": 1,
            "phases": [{"phase": "post_trade", "status": "warn"}],
            "action_items": ["补成交回写"],
        }
    )
    cli.run_review_timeline_watch(
        Namespace(
            state_log=tmp_path / "unused.jsonl",
            sqlite=sqlite_path,
            as_of="2026-05-30",
            repeat_threshold=2,
            stale_days=1,
            limit=10,
            format="markdown",
            output=None,
        )
    )
    markdown_output = capsys.readouterr().out
    assert "Trading Day Watchdog" in markdown_output
    assert "post_trade" in markdown_output


def test_review_lifecycle_history_can_read_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_trade_plan(
        {
            "created_at": "2026-05-29T09:00:00+00:00",
            "trade_date": "2026-05-29",
            "symbol": "000001",
            "strategy": "dragon",
            "status": "pass",
            "gate_status": "warn",
            "planned_value": 1000,
            "allowed_value": 800,
            "entry_price": 10,
        }
    )
    store.insert_trade({"date": "2026-05-29", "symbol": "000001", "side": "BUY", "price": 10, "quantity": 100, "reason": "buy", "amount": 1000})
    store.insert_position_action_plan({"created_at": "2026-05-29T10:00:00+00:00", "action_date": "2026-05-29", "status": "warn", "reduce_count": 1, "actions": []})
    store.insert_exit_plan({"created_at": "2026-05-29T11:00:00+00:00", "plan_date": "2026-05-29", "status": "block", "sell_all_count": 1, "expected_cash_release": 1000, "items": []})
    store.insert_lifecycle_snapshot(
        {
            "created_at": "2026-05-29T12:00:00+00:00",
            "snapshot_date": "2026-05-29",
            "status": "block",
            "execution": {
                "trade_plan_match_rate": 1.0,
                "action_execution_rate": 0.5,
                "exit_execution_rate": 0.0,
                "lot_exit_execution_rate": 0.0,
            },
        },
        snapshot_date="2026-05-29",
    )

    cli.run_review_lifecycle_history(
        Namespace(
            journal=tmp_path / "unused_trades.jsonl",
            sqlite=sqlite_path,
            trade_plan_log=tmp_path / "unused_trade_plans.jsonl",
            action_log=tmp_path / "unused_actions.jsonl",
            exit_log=tmp_path / "unused_exit.jsonl",
            lifecycle_log=tmp_path / "unused_lifecycle.jsonl",
            limit=20,
            format="markdown",
            output=None,
        )
    )

    output = capsys.readouterr().out
    assert "Review History" in output
    assert "Coverage" in output
    assert "sell-all" in output.lower()


def test_data_db_doctor_reports_review_gaps(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_trade({"date": "2026-05-30", "symbol": "000001", "side": "BUY", "price": 10, "quantity": 100, "reason": "buy", "amount": 1000})

    cli.run_data_db_doctor(
        Namespace(
            db_path=sqlite_path,
            format="markdown",
            output=None,
        )
    )

    output = capsys.readouterr().out
    assert "复盘医生" in output
    assert "交易计划" in output
    assert "执行确认" in output


def test_review_gates_cli_can_read_jsonl(tmp_path, capsys):
    journal_path = tmp_path / "trades.jsonl"
    journal_path.write_text(
        '{"date":"2026-05-29","symbol":"000001","side":"BUY","price":10,"quantity":100,"amount":1000,"strategy":"strong_stock_screen","gate_status":"warn","gate_message":"planned only","gate_reasons":["pretrade_warn"]}\n'
        '{"date":"2026-05-29","symbol":"000002","side":"BUY","price":12,"quantity":100,"amount":1200,"strategy":"strong_stock_screen","gate_status":"pass","gate_reasons":[]}\n',
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal_path,
        sqlite=None,
        strategy="strong_stock_screen",
        symbol="",
        limit=10,
        format="json",
        output=None,
    )

    cli.run_review_gates(args)

    output = capsys.readouterr().out
    assert '"gate_record_count": 2' in output
    assert '"violation_count": 1' in output
    assert '"pretrade_warn": 1' in output


def test_review_gates_cli_can_read_sqlite_and_write_markdown(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    output_path = tmp_path / "gate_review.md"
    store = SQLiteStore(sqlite_path)
    store.insert_trade(
        {
            "date": "2026-05-29",
            "symbol": "000001",
            "side": "BUY",
            "price": 10,
            "quantity": 100,
            "reason": "buy",
            "amount": 1000,
            "strategy": "strong_stock_screen",
            "gate_status": "block",
            "gate_message": "no new buys",
            "gate_reasons": ["data_health_failed"],
        }
    )
    args = Namespace(
        journal=tmp_path / "unused.jsonl",
        sqlite=sqlite_path,
        strategy="",
        symbol="000001",
        limit=10,
        format="markdown",
        output=output_path,
    )

    cli.run_review_gates(args)

    assert str(output_path) in capsys.readouterr().out
    content = output_path.read_text(encoding="utf-8")
    assert "# 门禁审计" in content
    assert "预警/阻断买入记录" in content
    assert "data_health_failed" in content


def test_review_exceptions_cli_can_read_jsonl(tmp_path, capsys):
    journal_path = tmp_path / "trades.jsonl"
    journal_path.write_text(
        '{"date":"2026-05-29","symbol":"000001","side":"BUY","price":10,"quantity":100,"amount":1000,"strategy":"dragon","discipline_exception":true,"exception_reason":"approved gap exception"}\n'
        '{"date":"2026-05-30","symbol":"000002","side":"BUY","price":12,"quantity":100,"amount":1200,"strategy":"dragon","discipline_exception":true,"exception_reason":""}\n',
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal_path,
        sqlite=None,
        limit=10,
        format="json",
        output=None,
    )

    cli.run_review_exceptions(args)

    output = capsys.readouterr().out
    assert '"exception_count": 2' in output
    assert '"missing_reason_count": 1' in output
    assert '"dragon": 2' in output


def test_review_exceptions_cli_can_read_sqlite_markdown(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    output_path = tmp_path / "exceptions.md"
    store = SQLiteStore(sqlite_path)
    store.insert_trade(
        {
            "date": "2026-05-29",
            "symbol": "000001",
            "side": "BUY",
            "price": 10,
            "quantity": 100,
            "reason": "buy",
            "amount": 1000,
            "strategy": "dragon",
            "discipline_exception": True,
            "exception_reason": "approved gap exception",
        }
    )
    args = Namespace(
        journal=tmp_path / "unused.jsonl",
        sqlite=sqlite_path,
        limit=10,
        format="markdown",
        output=output_path,
    )

    cli.run_review_exceptions(args)

    assert str(output_path) in capsys.readouterr().out
    content = output_path.read_text(encoding="utf-8")
    assert "# Discipline Exceptions" in content
    assert "approved gap exception" in content


def test_review_exceptions_markdown_includes_missing_reason_sources(tmp_path, capsys):
    journal_path = tmp_path / "trades.jsonl"
    journal_path.write_text(
        '{"date":"2026-05-29","symbol":"000001","side":"BUY","price":10,"quantity":100,"amount":1000,"strategy":"dragon","discipline_exception":true,"exception_reason":"approved gap exception"}\n'
        '{"date":"2026-05-30","symbol":"000002","side":"BUY","price":12,"quantity":100,"amount":1200,"strategy":"dragon","gate_status":"block","gate_reasons":["forced-gate-block"],"discipline_exception":true,"exception_reason":""}\n',
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal_path,
        sqlite=None,
        limit=10,
        format="markdown",
        output=None,
    )

    cli.run_review_exceptions(args)

    output = capsys.readouterr().out
    assert "## Missing Reasons" in output
    assert "gate:block" in output


def test_portfolio_positions_cli_can_read_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_trade({"date": "2024-01-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100, "reason": "buy", "amount": 1000})
    store.insert_trade({"date": "2024-01-02", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 12, "quantity": 100, "reason": "buy", "amount": 1200})
    store.insert_trade({"date": "2024-01-03", "symbol": "000001", "name": "Demo", "side": "SELL", "price": 13, "quantity": 100, "reason": "sell", "amount": 1300})
    args = Namespace(journal=tmp_path / "unused.jsonl", sqlite=sqlite_path, cash=10000, price=["000001=15"])

    cli.run_portfolio_positions(args)

    output = capsys.readouterr().out
    assert '"quantity": 100' in output
    assert '"avg_cost": 12.0' in output


def test_portfolio_risk_cli_can_read_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    SQLiteStore(sqlite_path).insert_trade(
        {
            "date": "2024-01-01",
            "symbol": "000001",
            "side": "BUY",
            "price": 10,
            "quantity": 100,
            "reason": "buy",
            "amount": 1000,
        }
    )
    args = Namespace(
        journal=tmp_path / "unused.jsonl",
        sqlite=sqlite_path,
        cash=10000,
        price=["000001=9"],
        stop=["000001=9.5"],
        max_exposure_pct=0.8,
        max_position_pct=0.2,
    )

    cli.run_portfolio_risk(args)

    output = capsys.readouterr().out
    assert '"status": "block"' in output
    assert '"name": "stop_loss"' in output


def test_review_constraints_cli_can_read_jsonl(tmp_path, capsys):
    log_path = tmp_path / "constraints.jsonl"
    log_path.write_text(
        '{"created_at":"2026-05-29T09:00:00+00:00","source":"portfolio.allocate","strategy":"dragon","alert_level":"warn","alerts":["execution_deviation"],"note":"demo"}\n',
        encoding="utf-8",
    )
    args = Namespace(log=log_path, sqlite=None, limit=10)

    cli.run_review_constraints(args)

    output = capsys.readouterr().out
    assert '"total": 1' in output
    assert '"warn_count": 1' in output
    assert '"execution_deviation": 1' in output


def test_review_constraints_cli_can_read_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    SQLiteStore(sqlite_path).insert_strategy_constraint(
        {
            "created_at": "2026-05-29T09:10:00+00:00",
            "source": "portfolio.precheck",
            "strategy": "dragon",
            "symbol": "000001",
            "alert_level": "block",
            "action": "pause",
            "alerts": ["mistake_cluster"],
            "note": "demo",
        }
    )
    args = Namespace(log=tmp_path / "unused.jsonl", sqlite=sqlite_path, limit=10)

    cli.run_review_constraints(args)

    output = capsys.readouterr().out
    assert '"total": 1' in output
    assert '"block_count": 1' in output
    assert '"mistake_cluster": 1' in output


def test_review_discipline_cli_can_read_jsonl(tmp_path, capsys):
    log_path = tmp_path / "discipline.jsonl"
    log_path.write_text(
        '{"created_at":"2026-05-29T09:00:00+00:00","date":"2026-05-29","source":"report.daily","status":"warn","advice":["Review gate violation"],"gate_violation_count":1,"missing_gate_count":0,"avg_execution_deviation_pct":0.03,"holding_status":"pass","target_exposure_pct":0.3,"allocated_pct":0.4}\n',
        encoding="utf-8",
    )
    args = Namespace(log=log_path, sqlite=None, limit=10, format="json")

    cli.run_review_discipline(args)

    output = capsys.readouterr().out
    assert '"total": 1' in output
    assert '"warn_count": 1' in output
    assert "Review gate violation" in output


def test_review_discipline_cli_can_read_sqlite_markdown(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    SQLiteStore(sqlite_path).insert_discipline_record(
        {
            "created_at": "2026-05-29T09:00:00+00:00",
            "date": "2026-05-29",
            "source": "report.premarket",
            "status": "block",
            "advice": ["No new positions"],
            "gate_violation_count": 0,
            "missing_gate_count": 0,
            "avg_execution_deviation_pct": 0,
            "holding_status": "block",
            "target_exposure_pct": 0,
            "allocated_pct": 0.1,
        }
    )
    args = Namespace(log=tmp_path / "unused.jsonl", sqlite=sqlite_path, limit=10, format="markdown")

    cli.run_review_discipline(args)

    output = capsys.readouterr().out
    assert "记录数：1" in output
    assert "通过/预警/阻断：0 / 0 / 1" in output
    assert "report.premarket" in output


def test_review_discipline_adherence_cli_can_read_jsonl(tmp_path, capsys):
    discipline_path = tmp_path / "discipline.jsonl"
    journal_path = tmp_path / "trades.jsonl"
    discipline_path.write_text(
        '{"created_at":"2026-05-29T09:00:00+00:00","date":"2026-05-29","source":"report.daily","status":"warn","advice":["Review every BUY executed under warn/block status."],"missing_gate_count":0}\n',
        encoding="utf-8",
    )
    journal_path.write_text(
        '{"date":"2026-05-30","symbol":"000001","side":"BUY","price":10,"quantity":100,"amount":1000,"gate_status":"warn","gate_message":"planned only"}\n',
        encoding="utf-8",
    )
    args = Namespace(
        log=discipline_path,
        discipline_log=None,
        journal=journal_path,
        sqlite=None,
        limit=10,
        lookahead_days=1,
        format="json",
        output=None,
    )

    cli.run_review_discipline_adherence(args)

    output = capsys.readouterr().out
    assert '"total": 1' in output
    assert '"warn_count": 1' in output
    assert "warn_block_buy_after_warn" in output


def test_review_discipline_adherence_cli_can_read_sqlite_markdown(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    output_path = tmp_path / "adherence.md"
    store = SQLiteStore(sqlite_path)
    store.insert_discipline_record(
        {
            "created_at": "2026-05-29T09:00:00+00:00",
            "date": "2026-05-29",
            "source": "report.premarket",
            "status": "block",
            "advice": ["No new positions"],
            "target_exposure_pct": 0,
            "allocated_pct": 0.1,
        }
    )
    store.insert_trade(
        {
            "date": "2026-05-29",
            "symbol": "000001",
            "side": "BUY",
            "price": 10,
            "quantity": 100,
            "reason": "buy",
            "amount": 1000,
            "gate_status": "block",
        }
    )
    args = Namespace(
        log=tmp_path / "unused.jsonl",
        discipline_log=None,
        journal=tmp_path / "unused_trades.jsonl",
        sqlite=sqlite_path,
        limit=10,
        lookahead_days=1,
        format="markdown",
        output=output_path,
    )

    cli.run_review_discipline_adherence(args)

    assert str(output_path) in capsys.readouterr().out
    content = output_path.read_text(encoding="utf-8")
    assert "# 纪律执行跟踪" in content
    assert "new_buy_after_block" in content
