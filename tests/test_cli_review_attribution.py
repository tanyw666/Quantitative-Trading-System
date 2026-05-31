import json

import quant_system.cli as cli


def test_review_attribution_cli_writes_json(tmp_path, capsys):
    trade_log, plan_log, confirm_log, approval_log, lifecycle_log = _write_attribution_logs(tmp_path)
    output = tmp_path / "attribution.json"
    args = cli.build_parser().parse_args(
        [
            "review",
            "attribution",
            "--trade-log",
            str(trade_log),
            "--plan-log",
            str(plan_log),
            "--confirm-log",
            str(confirm_log),
            "--approval-log",
            str(approval_log),
            "--lifecycle-log",
            str(lifecycle_log),
            "--format",
            "json",
            "--output",
            str(output),
        ]
    )

    cli.run_review_attribution(args)

    assert str(output) in capsys.readouterr().out
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "block"
    assert payload["summary"]["approval_cooldown_status"] == "block"
    assert payload["by_area"]["planning"] >= 1
    assert payload["by_area"]["approval"] >= 1
    assert payload["by_area"]["execution"] >= 1


def test_review_attribution_cli_writes_markdown(tmp_path, capsys):
    trade_log, plan_log, confirm_log, approval_log, lifecycle_log = _write_attribution_logs(tmp_path)
    output = tmp_path / "attribution.md"
    args = cli.build_parser().parse_args(
        [
            "review",
            "attribution",
            "--trade-log",
            str(trade_log),
            "--plan-log",
            str(plan_log),
            "--confirm-log",
            str(confirm_log),
            "--approval-log",
            str(approval_log),
            "--lifecycle-log",
            str(lifecycle_log),
            "--format",
            "markdown",
            "--output",
            str(output),
        ]
    )

    cli.run_review_attribution(args)

    assert str(output) in capsys.readouterr().out
    content = output.read_text(encoding="utf-8")
    assert "# 复盘归因" in content
    assert "approval_cooldown_block" in content
    assert "execution_block" in content


def test_review_attribution_policy_cli_records_constraints_and_discipline(tmp_path, capsys):
    trade_log, plan_log, confirm_log, approval_log, lifecycle_log = _write_attribution_logs(tmp_path)
    output = tmp_path / "attribution_policy.md"
    constraint_log = tmp_path / "constraints.jsonl"
    discipline_log = tmp_path / "discipline.jsonl"
    args = cli.build_parser().parse_args(
        [
            "review",
            "attribution-policy",
            "--trade-log",
            str(trade_log),
            "--plan-log",
            str(plan_log),
            "--confirm-log",
            str(confirm_log),
            "--approval-log",
            str(approval_log),
            "--lifecycle-log",
            str(lifecycle_log),
            "--constraint-log",
            str(constraint_log),
            "--discipline-log",
            str(discipline_log),
            "--effective-date",
            "2026-05-31",
            "--default-strategy",
            "dragon",
            "--record",
            "--format",
            "markdown",
            "--output",
            str(output),
        ]
    )

    cli.run_review_attribution_policy(args)

    assert str(output) in capsys.readouterr().out
    content = output.read_text(encoding="utf-8")
    assert "# Attribution Policy" in content
    assert "Next-Day Constraints" in content
    assert constraint_log.exists()
    assert discipline_log.exists()


def _write_attribution_logs(tmp_path):
    trade_log = tmp_path / "trades.jsonl"
    plan_log = tmp_path / "trade_plans.jsonl"
    confirm_log = tmp_path / "execution_confirms.jsonl"
    approval_log = tmp_path / "order_approvals.jsonl"
    lifecycle_log = tmp_path / "lifecycle_snapshots.jsonl"

    trade_log.write_text(
        json.dumps(
            {
                "date": "2026-05-30",
                "symbol": "000001",
                "side": "BUY",
                "strategy": "dragon",
                "price": 10.0,
                "quantity": 100,
                "amount": 1000,
                "order_approval_created_at": "2026-05-30T09:35:00+08:00",
                "gate_status": "block",
                "gate_reasons": ["market gate blocked"],
                "mistake_type": "chase",
                "discipline_exception": True,
                "review": "forced entry",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    plan_log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "trade_date": "2026-05-30",
                        "symbol": "000001",
                        "strategy": "dragon",
                        "status": "pass",
                        "gate_status": "pass",
                        "entry_price": 10.0,
                        "planned_pct": 0.1,
                        "planned_value": 1000,
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "trade_date": "2026-05-30",
                        "symbol": "000001",
                        "strategy": "dragon",
                        "status": "pass",
                        "gate_status": "pass",
                        "entry_price": 10.0,
                        "planned_pct": 0.1,
                        "planned_value": 1000,
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    confirm_log.write_text(
        json.dumps(
            {
                "created_at": "2026-05-30T09:30:00+08:00",
                "symbol": "000002",
                "status": "pass",
                "current_price": 8.0,
                "confirmed_value": 800,
                "suggested_quantity": 100,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    approval_log.write_text(
        json.dumps(
            {
                "created_at": "2026-05-30T09:35:00+08:00",
                "symbol": "000001",
                "strategy": "dragon",
                "status": "block",
                "confirmed_value": 0,
                "suggested_quantity": 0,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    lifecycle_log.write_text(
        json.dumps(
            {
                "created_at": "2026-05-30T15:10:00+08:00",
                "snapshot_date": "2026-05-30",
                "status": "warn",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return trade_log, plan_log, confirm_log, approval_log, lifecycle_log
