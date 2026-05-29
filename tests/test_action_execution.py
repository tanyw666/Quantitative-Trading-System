from argparse import Namespace
import json

import quant_system.cli as cli
from quant_system.portfolio.action_execution import summarize_action_execution


def test_action_execution_summary_detects_executed_and_missed_actions():
    action_records = [
        {
            "created_at": "2026-05-29T01:00:00+00:00",
            "action_date": "2026-05-29",
            "status": "warn",
            "actions": [
                {"symbol": "000001", "name": "Demo", "action": "exit", "current_quantity": 1000, "target_quantity": 0, "quantity_delta": -1000, "market_price": 9.0, "reason": "触发止损"},
                {"symbol": "000002", "name": "Demo2", "action": "reduce", "current_quantity": 1000, "target_quantity": 500, "quantity_delta": -500, "market_price": 10.0, "reason": "单票超限"},
            ],
        }
    ]
    trade_records = [
        {"date": "2026-05-29", "symbol": "000001", "side": "SELL", "price": 8.9, "quantity": 1000},
        {"date": "2026-05-30", "symbol": "000002", "side": "SELL", "price": 10.1, "quantity": 200},
    ]

    summary = summarize_action_execution(action_records, trade_records, lookahead_days=3, limit=10)

    assert summary["actionable_count"] == 2
    assert summary["executed_count"] == 1
    assert summary["partial_count"] == 1
    assert summary["missed_count"] == 0
    assert summary["execution_rate"] == 0.5


def test_review_action_execution_cli_outputs_summary(tmp_path, capsys):
    action_log = tmp_path / "position_actions.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    action_log.write_text(
        json.dumps(
            {
                "created_at": "2026-05-29T01:00:00+00:00",
                "action_date": "2026-05-29",
                "status": "warn",
                "actions": [
                    {"symbol": "000001", "name": "Demo", "action": "exit", "current_quantity": 1000, "target_quantity": 0, "quantity_delta": -1000, "market_price": 9.0, "reason": "触发止损"},
                ],
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
        action_log=action_log,
        trade_log=trade_log,
        sqlite=None,
        lookahead_days=3,
        limit=20,
        format="json",
        output=None,
    )

    cli.run_review_action_execution(args)

    output = capsys.readouterr().out
    assert '"executed_count": 1' in output
    assert '"execution_rate": 1.0' in output
