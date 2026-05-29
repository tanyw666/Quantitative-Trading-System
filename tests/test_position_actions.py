from argparse import Namespace
import json

from quant_system.portfolio.position_actions import build_position_action_plan, render_position_action_plan_lines
from quant_system.portfolio.positions import build_position_book
from quant_system.portfolio.risk_check import check_holding_risk
import quant_system.cli as cli


def test_position_action_plan_prioritizes_stop_loss_exit():
    records = [{"symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 1000}]
    book = build_position_book(records, cash=100000, prices={"000001": 9})
    risk = check_holding_risk(book, stops={"000001": 9.5})

    plan = build_position_action_plan(book, risk, stops={"000001": 9.5})

    payload = plan.to_dict()
    assert payload["status"] == "block"
    assert payload["exit_count"] == 1
    assert payload["actions"][0]["action"] == "exit"
    assert payload["actions"][0]["target_quantity"] == 0


def test_position_action_plan_reduces_overweight_holding():
    records = [{"symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 3000}]
    book = build_position_book(records, cash=100000, prices={"000001": 10})
    risk = check_holding_risk(book, max_position_pct=0.2)

    plan = build_position_action_plan(book, risk, max_position_pct=0.2)

    payload = plan.to_dict()
    assert payload["reduce_count"] == 1
    assert payload["actions"][0]["action"] == "reduce"
    assert payload["actions"][0]["target_quantity"] < 3000


def test_position_action_plan_markdown_renders_actions():
    records = [{"symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100}]
    book = build_position_book(records, cash=100000, prices={"000001": 10})
    risk = check_holding_risk(book)
    plan = build_position_action_plan(book, risk)

    lines = render_position_action_plan_lines(plan)

    assert any("总状态" in line for line in lines)
    assert any("000001" in line for line in lines)


def test_portfolio_actions_cli_outputs_action_plan(tmp_path, capsys):
    journal = tmp_path / "trades.jsonl"
    journal.write_text(
        json.dumps({"date": "2026-05-29", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 1000})
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal,
        sqlite=None,
        cash=100000,
        price=["000001=9"],
        stop=["000001=9.5"],
        max_exposure_pct=0.8,
        max_position_pct=0.2,
        target_exposure_pct=None,
        format="json",
        output=None,
    )

    cli.run_portfolio_actions(args)

    output = capsys.readouterr().out
    assert '"exit_count": 1' in output
    assert '"action": "exit"' in output


def test_portfolio_actions_cli_can_record_action_plan(tmp_path, capsys):
    journal = tmp_path / "trades.jsonl"
    action_log = tmp_path / "position_actions.jsonl"
    journal.write_text(
        json.dumps({"date": "2026-05-29", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 1000})
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal,
        sqlite=None,
        cash=100000,
        price=["000001=9"],
        stop=["000001=9.5"],
        max_exposure_pct=0.8,
        max_position_pct=0.2,
        target_exposure_pct=None,
        format="json",
        output=None,
        log=action_log,
        record=True,
    )

    cli.run_portfolio_actions(args)

    capsys.readouterr()
    saved = json.loads(action_log.read_text(encoding="utf-8").strip())
    assert saved["exit_count"] == 1
    assert saved["actions"][0]["action"] == "exit"
