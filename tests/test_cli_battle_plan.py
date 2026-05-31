import json

import quant_system.cli as cli


def test_run_battle_plan_report_writes_json(monkeypatch, tmp_path):
    output = tmp_path / "battle_plan.json"
    args = cli.build_parser().parse_args(
        [
            "report",
            "battle-plan",
            "--csv",
            "prices.csv",
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
            "allocation_plan": {"strategy_action": "pause", "strategy_alert_level": "block"},
            "holding_risk": {"status": "pass"},
            "holding_action_plan": {"status": "pass"},
            "exit_plan": {"status": "pass"},
            "pretrade_checks": [{"symbol": "000001", "status": "pass", "candidate_snapshot": {"name": "Demo"}}],
        },
    )

    cli.run_battle_plan_report(args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "block"
    assert payload["buy_candidates"] == []
    assert payload["blocked_candidates"][0]["symbol"] == "000001"
