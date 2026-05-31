import json

import quant_system.cli as cli


def test_run_assistant_report_writes_json(monkeypatch, tmp_path):
    output = tmp_path / "assistant.json"
    state_log = tmp_path / "states.jsonl"
    state_log.write_text(
        '{"created_at":"2026-05-29T15:30:00+08:00","date":"2026-05-29","source":"workflow.trading-day","status":"warn","phase_count":4,"pass_count":3,"warn_count":1,"block_count":0,"action_item_count":1,"phases":[{"phase":"intraday","status":"warn"}],"action_items":["check confirmations"]}\n',
        encoding="utf-8",
    )
    args = cli.build_parser().parse_args(
        [
            "report",
            "assistant",
            "--csv",
            "prices.csv",
            "--output",
            str(output),
            "--format",
            "json",
            "--state-log",
            str(state_log),
            "--as-of",
            "2026-05-30T10:00:00",
        ]
    )
    monkeypatch.setattr(
        cli,
        "_premarket_context_from_args",
        lambda _args: {
            "market_temperature": {"regime": "warm", "stance": "test"},
            "allocation_plan": {"target_exposure_pct": 0.3, "allocated_pct": 0.1},
            "final_battle_plan": {
                "status": "pass",
                "decision": "ok",
                "must_do": [],
                "buy_candidates": [{"symbol": "000001", "name": "Demo", "status": "pass", "planned_pct": 0.05, "allowed_pct": 0.05, "entry_price": 10, "stop_price": 9.5}],
                "blocked_candidates": [],
            },
            "approval_cooldown": {"status": "warn", "constraint_count": 1, "by_alert_level": {"warn": 1}, "action_items": ["slow down dragon"]},
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
    monkeypatch.setattr(cli, "_execution_confirmation_records_from_args", lambda _args: [])

    cli.run_assistant_report(args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] in {"warn", "block", "pass"}
    assert "cards" in payload
    assert "approval_cooldown" in payload["cards"]
    assert payload["buy_candidates"][0]["symbol"] == "000001"


def test_run_assistant_report_can_render_markdown(monkeypatch, tmp_path):
    output = tmp_path / "assistant.md"
    args = cli.build_parser().parse_args(
        [
            "report",
            "assistant",
            "--csv",
            "prices.csv",
            "--output",
            str(output),
            "--as-of",
            "2026-05-30",
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
    monkeypatch.setattr(cli, "_execution_confirmation_records_from_args", lambda _args: [])

    cli.run_assistant_report(args)

    content = output.read_text(encoding="utf-8")
    assert "# 交易助手" in content
    assert "## 审批冷静期" in content
    assert "## 交易日看板巡检" in content
