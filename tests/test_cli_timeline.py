import json

import quant_system.cli as cli
from quant_system.storage.sqlite_store import SQLiteStore


def test_run_timeline_report_writes_json(monkeypatch, tmp_path):
    output = tmp_path / "timeline.json"
    confirm_log = tmp_path / "execution_confirms.jsonl"
    state_log = tmp_path / "states.jsonl"
    sqlite_path = tmp_path / "quant.sqlite"
    settings_path = tmp_path / "system.yaml"
    settings_path.write_text(
        """
trading_day:
  phases:
    intraday:
      title: Intraday Template Phase
      extra_checklist:
        - Check live quote confirmation
""",
        encoding="utf-8",
    )
    confirm_log.write_text(
        '{"created_at":"2026-05-30T09:35:00+08:00","symbol":"000001","status":"warn"}\n',
        encoding="utf-8",
    )
    args = cli.build_parser().parse_args(
        [
            "report",
            "timeline",
            "--csv",
            "prices.csv",
            "--confirm-log",
            str(confirm_log),
            "--settings",
            str(settings_path),
            "--format",
            "json",
            "--output",
            str(output),
            "--as-of",
            "2026-05-30T10:00:00",
            "--record-state",
            "--state-log",
            str(state_log),
            "--sqlite",
            str(sqlite_path),
        ]
    )
    monkeypatch.setattr(
        cli,
        "_premarket_context_from_args",
        lambda _args: {
            "final_battle_plan": {"status": "pass", "buy_candidates": [{"symbol": "000001"}]},
            "lifecycle_snapshot": {"status": "pass"},
            "gate_review": {"violation_count": 0},
            "approval_cooldown": {"status": "pass", "constraint_count": 0},
        },
    )
    monkeypatch.setattr(cli, "_trade_records_from_args", lambda _args: [])
    monkeypatch.setattr(cli, "_execution_confirmation_records_from_args", lambda _args: [])

    cli.run_timeline_report(args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "warn"
    assert payload["phases"][1]["phase"] == "intraday"
    assert payload["phases"][1]["status"] == "warn"
    assert payload["phases"][1]["title"] == "Intraday Template Phase"
    assert payload["phases"][3]["phase"] == "approval_discipline"
    assert payload["action_items"]
    states = state_log.read_text(encoding="utf-8")
    assert '"source": "report.timeline"' in states
    assert len(SQLiteStore(sqlite_path).read_trading_day_states()) == 1


def test_run_timeline_report_can_render_markdown(monkeypatch, tmp_path):
    output = tmp_path / "timeline.md"
    args = cli.build_parser().parse_args(
        [
            "report",
            "timeline",
            "--csv",
            "prices.csv",
            "--output",
            str(output),
            "--as-of",
            "2026-05-30T15:30:00",
        ]
    )
    monkeypatch.setattr(
        cli,
        "_premarket_context_from_args",
        lambda _args: {
            "final_battle_plan": {"status": "pass", "buy_candidates": [], "blocked_candidates": []},
            "lifecycle_snapshot": {"status": "pass"},
            "gate_review": {"violation_count": 0},
            "approval_cooldown": {"status": "pass", "constraint_count": 0},
        },
    )
    monkeypatch.setattr(cli, "_trade_records_from_args", lambda _args: [])
    monkeypatch.setattr(cli, "_execution_confirmation_records_from_args", lambda _args: [])

    cli.run_timeline_report(args)

    content = output.read_text(encoding="utf-8")
    assert "# 交易日时间线" in content
    assert "审批纪律阶段" in content
