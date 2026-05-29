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
    assert payload["gate_reasons"] == ["交易前预检存在预警项"]
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
    assert "# Gate Review" in content
    assert "Warn/Block BUY Records" in content
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
    assert "Records: 1" in output
    assert "Pass/warn/block: 0 / 0 / 1" in output
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
    assert "# Discipline Adherence" in content
    assert "new_buy_after_block" in content
