from argparse import Namespace
import json

import quant_system.cli as cli
from quant_system.portfolio.exit_plan import (
    build_exit_plan,
    build_lot_exit_plan,
    render_exit_plan_lines,
    summarize_exit_execution,
    summarize_lot_exit_execution,
)
from quant_system.portfolio.lots import build_lot_book
from quant_system.portfolio.positions import build_position_book


def test_exit_plan_prioritizes_invalidated_thesis():
    records = [{"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 1000}]
    book = build_position_book(records, cash=100000, prices={"000001": 11})

    plan = build_exit_plan(book, trade_records=records, invalidated={"000001": "leader failed"}, plan_date="2026-05-29")

    payload = plan.to_dict()
    assert payload["status"] == "block"
    assert payload["sell_all_count"] == 1
    assert payload["invalidated_count"] == 1
    assert payload["items"][0]["plan_type"] == "strategy_invalidated"
    assert payload["items"][0]["sell_quantity"] == 1000


def test_exit_plan_takes_partial_profit_by_lot():
    records = [{"date": "2026-05-20", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 1000}]
    book = build_position_book(records, cash=100000, prices={"000001": 13})

    plan = build_exit_plan(book, trade_records=records, targets={"000001": 12}, profit_take_pct=0.5)

    item = plan.to_dict()["items"][0]
    assert plan.take_profit_count == 1
    assert item["action"] == "sell_partial"
    assert item["sell_quantity"] == 500
    assert item["target_quantity"] == 500


def test_exit_plan_time_stop_when_holding_too_long_without_return():
    records = [{"date": "2026-04-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 1000}]
    book = build_position_book(records, cash=100000, prices={"000001": 10})

    plan = build_exit_plan(book, trade_records=records, max_holding_days=20, plan_date="2026-05-01")

    item = plan.to_dict()["items"][0]
    assert plan.time_stop_count == 1
    assert item["plan_type"] == "time_stop"
    assert item["sell_quantity"] == 1000


def test_exit_plan_markdown_renders_items():
    records = [{"date": "2026-05-20", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 1000}]
    book = build_position_book(records, cash=100000, prices={"000001": 13})
    plan = build_exit_plan(book, trade_records=records, targets={"000001": 12})

    lines = render_exit_plan_lines(plan)

    assert any("Status:" in line for line in lines)
    assert any("000001" in line for line in lines)


def test_lot_exit_plan_targets_specific_buy_lot():
    records = [
        {"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100},
        {"date": "2026-05-20", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 12, "quantity": 100},
    ]
    lot_book = build_lot_book(records, prices={"000001": 13}, as_of="2026-05-29").to_dict()

    plan = build_lot_exit_plan(lot_book, targets={"000001": 12.5}, profit_take_pct=0.5)

    payload = plan.to_dict()
    assert payload["take_profit_count"] == 2
    assert payload["items"][0]["lot_id"]
    assert payload["items"][0]["entry_date"] in {"2026-05-01", "2026-05-20"}
    assert payload["total_sell_quantity"] == 200


def test_lot_exit_plan_time_stops_only_stale_lot_when_new_lot_is_profitable_enough():
    records = [
        {"date": "2026-04-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100},
        {"date": "2026-05-25", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 9, "quantity": 100},
    ]
    lot_book = build_lot_book(records, prices={"000001": 9.5}, as_of="2026-05-29").to_dict()

    plan = build_lot_exit_plan(lot_book, max_holding_days=20, plan_date="2026-05-29")

    items = plan.to_dict()["items"]
    assert sum(1 for item in items if item["plan_type"] == "time_stop") == 1
    assert next(item for item in items if item["plan_type"] == "time_stop")["entry_date"] == "2026-04-01"


def test_lot_exit_execution_matches_intended_closed_lot():
    records = [
        {"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100},
        {"date": "2026-05-20", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 12, "quantity": 100},
        {"date": "2026-05-30", "symbol": "000001", "name": "Demo", "side": "SELL", "price": 13, "quantity": 100},
    ]
    exit_records = [
        {
            "plan_date": "2026-05-29",
            "items": [
                {
                    "symbol": "000001",
                    "lot_id": "000001-2026-05-01-1",
                    "entry_date": "2026-05-01",
                    "plan_type": "take_profit",
                    "action": "sell_all",
                    "sell_quantity": 100,
                    "market_price": 13,
                }
            ],
        }
    ]

    summary = summarize_lot_exit_execution(exit_records, records, lookahead_days=3)

    assert summary["actionable_count"] == 1
    assert summary["executed_count"] == 1
    assert summary["records"][0]["lot_id"] == "000001-2026-05-01-1"


def test_lot_exit_execution_detects_wrong_lot_sold():
    records = [
        {"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100},
        {"date": "2026-05-20", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 12, "quantity": 100},
        {"date": "2026-05-30", "symbol": "000001", "name": "Demo", "side": "SELL", "price": 13, "quantity": 100},
    ]
    exit_records = [
        {
            "plan_date": "2026-05-29",
            "items": [
                {
                    "symbol": "000001",
                    "lot_id": "000001-2026-05-20-2",
                    "entry_date": "2026-05-20",
                    "plan_type": "take_profit",
                    "action": "sell_all",
                    "sell_quantity": 100,
                    "market_price": 13,
                }
            ],
        }
    ]

    summary = summarize_lot_exit_execution(exit_records, records, lookahead_days=3)

    assert summary["missed_count"] == 1
    assert "wrong batch" in summary["action_items"][0]


def test_exit_execution_audit_matches_sell_trades():
    exit_records = [
        {
            "plan_date": "2026-05-29",
            "items": [
                {"symbol": "000001", "plan_type": "stop_loss", "action": "sell_all", "sell_quantity": 1000, "market_price": 9},
                {"symbol": "000002", "plan_type": "take_profit", "action": "sell_partial", "sell_quantity": 500, "market_price": 12},
            ],
        }
    ]
    trade_records = [
        {"date": "2026-05-29", "symbol": "000001", "side": "SELL", "price": 8.9, "quantity": 1000},
        {"date": "2026-05-30", "symbol": "000002", "side": "SELL", "price": 12.2, "quantity": 200},
    ]

    summary = summarize_exit_execution(exit_records, trade_records, lookahead_days=3)

    assert summary["actionable_count"] == 2
    assert summary["executed_count"] == 1
    assert summary["partial_count"] == 1
    assert summary["missed_count"] == 0


def test_portfolio_exit_plan_cli_can_record(tmp_path, capsys):
    journal = tmp_path / "trades.jsonl"
    exit_log = tmp_path / "exit_plans.jsonl"
    journal.write_text(
        json.dumps({"date": "2026-05-20", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 1000})
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal,
        sqlite=None,
        cash=100000,
        price=["000001=9"],
        stop=["000001=9.5"],
        target=[],
        invalidate=[],
        max_position_pct=0.2,
        max_holding_days=20,
        time_stop_min_return_pct=0.0,
        profit_take_pct=0.5,
        plan_date="2026-05-29",
        lot_level=False,
        format="json",
        output=None,
        log=exit_log,
        record=True,
    )

    cli.run_portfolio_exit_plan(args)

    output = capsys.readouterr().out
    saved = json.loads(exit_log.read_text(encoding="utf-8").strip())
    assert '"plan_type": "stop_loss"' in output
    assert saved["sell_all_count"] == 1


def test_portfolio_exit_plan_cli_supports_lot_level(tmp_path, capsys):
    journal = tmp_path / "trades.jsonl"
    journal.write_text(
        json.dumps({"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100})
        + "\n"
        + json.dumps({"date": "2026-05-20", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 12, "quantity": 100})
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal,
        sqlite=None,
        cash=100000,
        price=["000001=13"],
        stop=[],
        target=["000001=12.5"],
        invalidate=[],
        max_position_pct=0.2,
        max_holding_days=20,
        time_stop_min_return_pct=0.0,
        profit_take_pct=0.5,
        plan_date="2026-05-29",
        lot_level=True,
        format="json",
        output=None,
        log=tmp_path / "exit_plans.jsonl",
        record=False,
    )

    cli.run_portfolio_exit_plan(args)

    output = capsys.readouterr().out
    assert '"lot_id": "000001-2026-05-01-1"' in output
    assert '"take_profit_count": 2' in output


def test_review_exit_audit_cli_outputs_summary(tmp_path, capsys):
    exit_log = tmp_path / "exit_plans.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    exit_log.write_text(
        json.dumps(
            {
                "plan_date": "2026-05-29",
                "items": [{"symbol": "000001", "plan_type": "stop_loss", "action": "sell_all", "sell_quantity": 1000, "market_price": 9}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    trade_log.write_text(
        json.dumps({"date": "2026-05-29", "symbol": "000001", "side": "SELL", "price": 8.9, "quantity": 1000}) + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        exit_log=exit_log,
        trade_log=trade_log,
        sqlite=None,
        lookahead_days=3,
        limit=20,
        format="json",
        output=None,
    )

    cli.run_review_exit_audit(args)

    output = capsys.readouterr().out
    assert '"executed_count": 1' in output
    assert '"execution_rate": 1.0' in output


def test_review_lot_exit_audit_cli_outputs_summary(tmp_path, capsys):
    exit_log = tmp_path / "exit_plans.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    exit_log.write_text(
        json.dumps(
            {
                "plan_date": "2026-05-29",
                "items": [
                    {
                        "symbol": "000001",
                        "lot_id": "000001-2026-05-01-1",
                        "entry_date": "2026-05-01",
                        "plan_type": "take_profit",
                        "action": "sell_all",
                        "sell_quantity": 100,
                        "market_price": 13,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    trade_log.write_text(
        json.dumps({"date": "2026-05-01", "symbol": "000001", "side": "BUY", "price": 10, "quantity": 100})
        + "\n"
        + json.dumps({"date": "2026-05-30", "symbol": "000001", "side": "SELL", "price": 13, "quantity": 100})
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        exit_log=exit_log,
        trade_log=trade_log,
        sqlite=None,
        lookahead_days=3,
        limit=20,
        format="json",
        output=None,
    )

    cli.run_review_lot_exit_audit(args)

    output = capsys.readouterr().out
    assert '"executed_count": 1' in output
    assert '"lot_id": "000001-2026-05-01-1"' in output
