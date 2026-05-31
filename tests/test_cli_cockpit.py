from types import SimpleNamespace
import json

import quant_system.cli as cli


def test_run_cockpit_report_writes_json(monkeypatch, tmp_path):
    output = tmp_path / "cockpit.json"
    confirm_log = tmp_path / "execution_confirms.jsonl"
    confirm_log.write_text(
        '{"created_at":"2026-05-30T09:30:00+00:00","symbol":"000001","status":"warn"}\n',
        encoding="utf-8",
    )
    args = cli.build_parser().parse_args(
        [
            "report",
            "cockpit",
            "--csv",
            "prices.csv",
            "--confirm-log",
            str(confirm_log),
            "--format",
            "json",
            "--output",
            str(output),
        ]
    )
    monkeypatch.setattr(
        cli,
        "_premarket_context_from_args",
        lambda _args: {
            "market_temperature": {"regime": "warm", "stance": "test"},
            "allocation_plan": {"target_exposure_pct": 0.3, "allocated_pct": 0.1},
            "final_battle_plan": {"status": "warn", "decision": "reduce", "must_do": [], "buy_candidates": [], "blocked_candidates": []},
            "approval_cooldown": {"status": "warn", "constraint_count": 1, "by_alert_level": {"warn": 1}},
            "holding_risk": {"status": "pass"},
            "holding_action_plan": {"status": "pass"},
            "exit_plan": {"status": "pass"},
            "lifecycle_snapshot": {"status": "pass"},
            "pretrade_checks": [],
            "gate_review": {"violation_count": 0},
        },
    )
    monkeypatch.setattr(cli, "_trade_records_from_args", lambda _args: [{"date": "2026-05-30", "symbol": "000001", "side": "BUY", "price": 10, "quantity": 100, "amount": 1000, "review": "ok"}])
    monkeypatch.setattr(cli, "_trade_plan_records_from_args", lambda _args: [{"trade_date": "2026-05-30", "symbol": "000001", "status": "pass", "gate_status": "warn", "planned_pct": 0.1, "planned_value": 1000, "entry_price": 10}])

    cli.run_cockpit_report(args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] in {"warn", "pass"}
    assert "approval_cooldown" in payload
    assert "execution_audit" in payload
    assert "final_battle_plan" in payload


def test_run_cockpit_report_can_render_markdown(monkeypatch, tmp_path):
    output = tmp_path / "cockpit.md"
    args = cli.build_parser().parse_args(
        [
            "report",
            "cockpit",
            "--csv",
            "prices.csv",
            "--output",
            str(output),
        ]
    )
    monkeypatch.setattr(
        cli,
        "_premarket_context_from_args",
        lambda _args: {
            "market_temperature": {"regime": "warm", "stance": "test"},
            "allocation_plan": {"target_exposure_pct": 0.3, "allocated_pct": 0.1},
            "final_battle_plan": {"status": "pass", "decision": "ok", "must_do": [], "buy_candidates": [], "blocked_candidates": []},
            "approval_cooldown": {"status": "pass", "constraint_count": 0},
            "holding_risk": {"status": "pass"},
            "holding_action_plan": {"status": "pass"},
            "exit_plan": {"status": "pass"},
            "lifecycle_snapshot": {"status": "pass"},
            "pretrade_checks": [],
            "gate_review": {"violation_count": 0},
        },
    )
    monkeypatch.setattr(cli, "_trade_records_from_args", lambda _args: [])
    monkeypatch.setattr(cli, "_trade_plan_records_from_args", lambda _args: [])

    cli.run_cockpit_report(args)

    content = output.read_text(encoding="utf-8")
    assert "# 交易驾驶舱" in content
    assert "最终作战单" in content
    assert "审批冷静期" in content
