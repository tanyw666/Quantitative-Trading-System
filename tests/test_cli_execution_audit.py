from argparse import Namespace
import json

import quant_system.cli as cli


def test_review_trade_add_attaches_execution_confirmation(tmp_path, capsys):
    confirm_path = tmp_path / "confirm.json"
    confirm_path.write_text(
        json.dumps(
            {
                "created_at": "2026-05-30T09:30:00+00:00",
                "symbol": "000001",
                "status": "warn",
                "decision": "WARN: reduced-size confirmation only",
                "current_price": 10.0,
                "reference_price": 9.9,
                "confirmed_pct": 0.05,
                "confirmed_value": 5000,
                "suggested_quantity": 500,
                "checks": [{"status": "warn", "message": "price drift"}],
                "pretrade_result": {"stop_price": 9.5, "target_price": 11.5, "candidate_snapshot": {"name": "Demo"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = Namespace(
        journal=tmp_path / "trades.jsonl",
        sqlite=None,
        date="2026-05-30",
        symbol="000001",
        side="BUY",
        price=10.05,
        quantity=500,
        reason="confirmed",
        name="",
        strategy="",
        market_regime="warm",
        planned_pct=0,
        actual_pct=0,
        planned_price=None,
        stop_price=None,
        target_price=None,
        tags="",
        mistake_type="",
        review="followed confirmation",
        workflow_summary=None,
        trade_plan=None,
        execution_confirm=confirm_path,
        order_approval=None,
        gate_status="",
        gate_message="",
        gate_reason=[],
        discipline_exception=False,
        exception_reason="",
    )

    cli.run_review_trade_add(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_confirmation_status"] == "warn"
    assert payload["execution_confirmation_created_at"] == "2026-05-30T09:30:00+00:00"
    assert payload["planned_price"] == 10.0
    assert payload["planned_pct"] == 0.05
    assert payload["suggested_quantity"] == 500
    assert "execution-confirm" in payload["tags"]
    assert "confirm-warn" in payload["tags"]


def test_review_trade_add_attaches_order_approval(tmp_path, capsys):
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(
        json.dumps(
            {
                "created_at": "2026-05-30T09:40:00+00:00",
                "symbol": "000001",
                "status": "pass",
                "decision": "PASS",
                "confirmed_pct": 0.1,
                "confirmed_value": 10000,
                "suggested_quantity": 1000,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = Namespace(
        journal=tmp_path / "trades.jsonl",
        sqlite=None,
        date="2026-05-30",
        symbol="000001",
        side="BUY",
        price=10,
        quantity=1000,
        reason="approved",
        name="",
        strategy="",
        market_regime="warm",
        planned_pct=0,
        actual_pct=0,
        planned_price=None,
        stop_price=None,
        target_price=None,
        tags="",
        mistake_type="",
        review="followed approval",
        workflow_summary=None,
        trade_plan=None,
        execution_confirm=None,
        order_approval=approval_path,
        gate_status="",
        gate_message="",
        gate_reason=[],
        discipline_exception=False,
        exception_reason="",
    )

    cli.run_review_trade_add(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["order_approval_created_at"] == "2026-05-30T09:40:00+00:00"
    assert payload["order_approval_status"] == "pass"
    assert payload["approved_quantity"] == 1000
    assert "order-approval" in payload["tags"]
    assert "approval-pass" in payload["tags"]


def test_review_trade_add_auto_marks_forced_buy_exception(tmp_path, capsys):
    confirm_path = tmp_path / "confirm.json"
    confirm_path.write_text(
        json.dumps(
            {
                "created_at": "2026-05-30T09:30:00+00:00",
                "symbol": "000001",
                "status": "pass",
                "decision": "PASS",
                "current_price": 10.0,
                "confirmed_pct": 0.05,
                "confirmed_value": 5000,
                "suggested_quantity": 500,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = Namespace(
        journal=tmp_path / "trades.jsonl",
        sqlite=None,
        date="2026-05-30",
        symbol="000001",
        side="BUY",
        price=10.2,
        quantity=800,
        reason="manual override",
        name="",
        strategy="",
        market_regime="warm",
        planned_pct=0,
        actual_pct=0,
        planned_price=None,
        stop_price=None,
        target_price=None,
        tags="",
        mistake_type="",
        review="forced trade",
        workflow_summary=None,
        trade_plan=None,
        execution_confirm=confirm_path,
        order_approval=None,
        gate_status="block",
        gate_message="no new buys",
        gate_reason=[],
        discipline_exception=False,
        exception_reason="",
    )

    cli.run_review_trade_add(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["discipline_exception"] is True
    assert payload["exception_reason"] == ""
    assert "exception-missing-reason" in payload["tags"]
    assert "forced-gate-block" in payload["gate_reasons"]
    assert "forced-confirm-size-exceeded" in payload["gate_reasons"]


def test_review_execution_audit_cli_outputs_markdown(tmp_path, capsys):
    confirm_log = tmp_path / "execution_confirms.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    confirm_log.write_text(
        '{"created_at":"2026-05-30T09:30:00+00:00","symbol":"000001","status":"pass","current_price":10,"confirmed_value":10000,"suggested_quantity":1000}\n',
        encoding="utf-8",
    )
    trade_log.write_text(
        '{"date":"2026-05-30","symbol":"000001","side":"BUY","price":10.1,"quantity":1000,"amount":10100,"execution_confirmation_created_at":"2026-05-30T09:30:00+00:00","review":"ok"}\n',
        encoding="utf-8",
    )
    output = tmp_path / "audit.md"
    args = Namespace(
        confirm_log=confirm_log,
        trade_log=trade_log,
        journal=trade_log,
        sqlite=None,
        lookahead_days=1,
        limit=10,
        format="markdown",
        output=output,
    )

    cli.run_review_execution_audit(args)

    assert str(output) in capsys.readouterr().out
    content = output.read_text(encoding="utf-8")
    assert "# Execution Audit" in content
    assert "Matched trades: 1" in content


def test_review_approval_audit_cli_outputs_markdown(tmp_path, capsys):
    approval_log = tmp_path / "order_approvals.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    approval_log.write_text(
        '{"created_at":"2026-05-30T09:30:00+00:00","symbol":"000001","status":"pass","confirmed_value":10000,"suggested_quantity":1000}\n',
        encoding="utf-8",
    )
    trade_log.write_text(
        '{"date":"2026-05-30","symbol":"000001","side":"BUY","price":10,"quantity":1000,"amount":10000,"order_approval_created_at":"2026-05-30T09:30:00+00:00","review":"ok"}\n',
        encoding="utf-8",
    )
    output = tmp_path / "approval_audit.md"
    args = Namespace(
        approval_log=approval_log,
        trade_log=trade_log,
        journal=trade_log,
        sqlite=None,
        lookahead_days=1,
        value_tolerance_pct=0.02,
        limit=10,
        format="markdown",
        output=output,
    )

    cli.run_review_approval_audit(args)

    assert str(output) in capsys.readouterr().out
    content = output.read_text(encoding="utf-8")
    assert "# Approval Execution Audit" in content
    assert "Matched trades: 1" in content
