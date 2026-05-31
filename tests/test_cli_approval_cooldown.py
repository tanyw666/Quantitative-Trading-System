from argparse import Namespace
import json

import quant_system.cli as cli


def test_review_approval_cooldown_cli_persists_constraint(tmp_path, capsys):
    approval_log = tmp_path / "order_approvals.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    constraint_log = tmp_path / "constraints.jsonl"
    approval_log.write_text(
        '{"created_at":"2026-05-30T09:30:00+00:00","symbol":"000001","status":"block","confirmed_value":0,"suggested_quantity":0,"strategy":"dragon"}\n',
        encoding="utf-8",
    )
    trade_log.write_text(
        '{"date":"2026-05-30","symbol":"000001","strategy":"dragon","side":"BUY","price":10,"quantity":100,"amount":1000,"order_approval_created_at":"2026-05-30T09:30:00+00:00","review":"violation"}\n',
        encoding="utf-8",
    )
    output = tmp_path / "approval_cooldown.md"
    args = Namespace(
        approval_log=approval_log,
        trade_log=trade_log,
        journal=trade_log,
        sqlite=None,
        constraint_log=constraint_log,
        lookahead_days=1,
        value_tolerance_pct=0.02,
        block_threshold=1,
        warn_threshold=2,
        fallback_threshold=2,
        warn_exposure_multiplier=0.5,
        limit=10,
        record=True,
        format="markdown",
        output=output,
    )

    cli.run_review_approval_cooldown(args)

    assert str(output) in capsys.readouterr().out
    assert constraint_log.exists()
    payload = json.loads(constraint_log.read_text(encoding="utf-8").strip())
    assert payload["strategy"] == "dragon"
    assert payload["alert_level"] == "block"
    assert payload["action"] == "pause"
    content = output.read_text(encoding="utf-8")
    assert "# 审批冷静期" in content
