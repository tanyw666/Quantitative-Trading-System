from argparse import Namespace
import json
from pathlib import Path

import pandas as pd

import quant_system.cli as cli


def test_workflow_premarket_accepts_refresh_args():
    args = cli.build_parser().parse_args(
        [
            "workflow",
            "premarket",
            "--csv",
            "prices.csv",
            "--refresh-cache",
            "--refresh-start",
            "20240101",
            "--battle-plan-output",
            "battle_plan.md",
            "--approval-log",
            "order_approvals.jsonl",
            "--record-approval-cooldown",
            "--approval-warn-threshold",
            "3",
        ]
    )

    assert args.workflow_command == "premarket"
    assert args.refresh_cache is True
    assert args.refresh_start == "20240101"
    assert str(args.battle_plan_output) == "battle_plan.md"
    assert args.approval_log == Path("order_approvals.jsonl")
    assert args.record_approval_cooldown is True
    assert args.approval_warn_threshold == 3


def test_workflow_trading_day_accepts_report_outputs():
    args = cli.build_parser().parse_args(
        [
            "workflow",
            "trading-day",
            "--csv",
            "prices.csv",
            "--premarket-output",
            "premarket.md",
            "--battle-plan-output",
            "battle.md",
            "--cockpit-output",
            "cockpit.md",
            "--execution-audit-output",
            "execution.md",
            "--lifecycle-output",
            "lifecycle.md",
            "--timeline-output",
            "timeline.md",
            "--assistant-output",
            "assistant.md",
            "--daily-output",
            "today.md",
            "--trade-plan-batch-output",
            "trade_plan_batch.md",
            "--review-doctor-output",
            "review_doctor.md",
            "--review-attribution-output",
            "review_attribution.md",
            "--attribution-policy-output",
            "attribution_policy.md",
            "--record-attribution-policy",
            "--attribution-policy-date",
            "2026-05-31",
            "--record-state",
            "--state-log",
            "timeline_states.jsonl",
            "--record-trade-plans",
            "--trade-plan-log",
            "trade_plans.jsonl",
            "--summary-output",
            "summary.json",
            "--approval-log",
            "order_approvals.jsonl",
            "--record-approval-cooldown",
        ]
    )

    assert args.workflow_command == "trading-day"
    assert str(args.premarket_output) == "premarket.md"
    assert str(args.cockpit_output) == "cockpit.md"
    assert str(args.timeline_output) == "timeline.md"
    assert str(args.assistant_output) == "assistant.md"
    assert str(args.daily_output) == "today.md"
    assert str(args.trade_plan_batch_output) == "trade_plan_batch.md"
    assert str(args.review_doctor_output) == "review_doctor.md"
    assert str(args.review_attribution_output) == "review_attribution.md"
    assert str(args.attribution_policy_output) == "attribution_policy.md"
    assert args.record_attribution_policy is True
    assert args.attribution_policy_date == "2026-05-31"
    assert args.record_state is True
    assert str(args.state_log) == "timeline_states.jsonl"
    assert args.record_trade_plans is True
    assert str(args.trade_plan_log) == "trade_plans.jsonl"
    assert str(args.summary_output) == "summary.json"
    assert args.approval_log == Path("order_approvals.jsonl")
    assert args.record_approval_cooldown is True


def test_workflow_daily_shortcut_uses_trading_day_args():
    args = cli.build_parser().parse_args(
        [
            "workflow",
            "daily",
            "--csv",
            "prices.csv",
            "--daily-output",
            "today.md",
            "--summary-output",
            "summary.json",
        ]
    )

    assert args.workflow_command == "daily"
    assert str(args.daily_output) == "today.md"
    assert str(args.summary_output) == "summary.json"


def test_run_workflow_premarket_runs_end_to_end(monkeypatch, tmp_path, capsys):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2024-01-01,000001,10,11,9,10,1000\n"
        "2024-01-02,000001,10,12,9,11,1000\n",
        encoding="utf-8",
    )
    report_path = tmp_path / "premarket.md"
    summary_path = tmp_path / "workflow.json"
    battle_plan_path = tmp_path / "battle_plan.md"

    args = Namespace(
        command="workflow",
        csv=csv_path,
        cache_dir=tmp_path / "cache",
        universe=None,
        strategy="strong_stock_screen",
        config=None,
        settings=None,
        tracker=tmp_path / "selections.jsonl",
        journal=tmp_path / "trades.jsonl",
        sqlite=None,
        top=5,
        cash=100000,
        max_positions=5,
        experiment_summary=None,
        promotion_log=None,
        constraint_log=None,
        rotation_snapshot_dir=None,
        sector_column=None,
        sector_top=5,
        only_top_sectors=False,
        price=[],
        stop=[],
        max_exposure_pct=0.8,
        max_position_pct=0.2,
        output=report_path,
        summary_output=summary_path,
        battle_plan_output=battle_plan_path,
        strict=False,
        min_rows=1,
        max_stale_days=10,
        as_of="2024-01-02",
        refresh_cache=False,
        refresh_start=None,
        refresh_end=None,
        adjust="qfq",
        source="auto",
        manifest=tmp_path / "manifest.jsonl",
        limit=None,
        refresh_stale_days=None,
        record_discipline=True,
        discipline_log=tmp_path / "discipline.jsonl",
        target=[],
        invalidate=[],
        max_holding_days=20,
        time_stop_min_return_pct=0.0,
        profit_take_pct=0.5,
        action_log=tmp_path / "position_actions.jsonl",
        record_actions=False,
        exit_log=tmp_path / "exit_plans.jsonl",
        record_exit_plan=False,
    )

    monkeypatch.setattr(cli, "load_ohlcv_dataset", lambda *a, **k: pd.read_csv(csv_path))
    monkeypatch.setattr(
        cli,
        "_premarket_context_from_args",
        lambda *a, **k: {
            "market_temperature": {"regime": "warm"},
            "pretrade_checks": [{"status": "pass"}],
            "holding_risk": {"status": "pass"},
        },
    )
    monkeypatch.setattr(cli, "run_premarket_report", lambda a, **kwargs: report_path.write_text("# report", encoding="utf-8"))

    cli.run_workflow_premarket(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] in {"ok", "warn"}
    assert payload["gate"]["status"] == "pass"
    assert any(step["name"] == "data_health" for step in payload["steps"])
    assert payload["outputs"]["battle_plan"] == str(battle_plan_path)
    assert report_path.exists()
    assert summary_path.exists()
    assert battle_plan_path.exists()
    assert "最终门禁" in battle_plan_path.read_text(encoding="utf-8")
    assert args.discipline_log.exists()


def test_run_workflow_premarket_records_bad_cache_as_load_failure(monkeypatch, tmp_path, capsys):
    summary_path = tmp_path / "workflow.json"
    args = Namespace(
        command="workflow",
        csv=None,
        cache_dir=tmp_path / "cache",
        universe=tmp_path / "universe.csv",
        output=tmp_path / "premarket.md",
        summary_output=summary_path,
        refresh_cache=False,
        strict=False,
    )
    monkeypatch.setattr(cli, "load_ohlcv_dataset", lambda *a, **k: (_ for _ in ()).throw(ValueError("cached symbol mismatch")))

    try:
        cli.run_workflow_premarket(args)
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Expected SystemExit")

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "fail"
    assert payload["steps"][-1]["name"] == "load_data"
    assert "cached symbol mismatch" in payload["steps"][-1]["message"]
    assert json.loads(summary_path.read_text(encoding="utf-8"))["status"] == "fail"


def test_run_workflow_trading_day_writes_all_outputs(monkeypatch, tmp_path, capsys):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2024-01-01,000001,10,11,9,10,1000\n"
        "2024-01-02,000001,10,12,9,11,1000\n",
        encoding="utf-8",
    )
    args = cli.build_parser().parse_args(
        [
            "workflow",
            "trading-day",
            "--csv",
            str(csv_path),
            "--premarket-output",
            str(tmp_path / "premarket.md"),
            "--battle-plan-output",
            str(tmp_path / "battle.md"),
            "--cockpit-output",
            str(tmp_path / "cockpit.md"),
            "--execution-audit-output",
            str(tmp_path / "execution.md"),
            "--lifecycle-output",
            str(tmp_path / "lifecycle.md"),
            "--timeline-output",
            str(tmp_path / "timeline.md"),
            "--assistant-output",
            str(tmp_path / "assistant.md"),
            "--daily-output",
            str(tmp_path / "today.md"),
            "--trade-plan-batch-output",
            str(tmp_path / "trade_plan_batch.md"),
            "--review-doctor-output",
            str(tmp_path / "review_doctor.md"),
            "--review-attribution-output",
            str(tmp_path / "review_attribution.md"),
            "--attribution-policy-output",
            str(tmp_path / "attribution_policy.md"),
            "--record-state",
            "--state-log",
            str(tmp_path / "timeline_states.jsonl"),
            "--record-trade-plans",
            "--trade-plan-log",
            str(tmp_path / "trade_plans.jsonl"),
            "--summary-output",
            str(tmp_path / "summary.json"),
            "--min-rows",
            "1",
            "--max-stale-days",
            "10",
            "--as-of",
            "2024-01-02",
        ]
    )
    context = {
        "market_temperature": {"regime": "warm", "stance": "test"},
        "market_context": {},
        "data_health": {"status": "ok"},
        "candidates": [],
        "allocation_plan": {"target_exposure_pct": 0.3, "allocated_pct": 0.1},
        "pretrade_checks": [{"status": "pass"}],
        "position_book": {},
        "lot_book": {},
        "holding_risk": {"status": "pass"},
        "holding_action_plan": {"status": "pass"},
        "exit_plan": {"status": "pass"},
        "strategy_health": [],
        "constraint_summary": {},
        "strategy_rotation": [],
        "rotation_history": {},
        "gate_review": {"violation_count": 0},
        "trade_stats": {},
        "action_execution_summary": {},
        "exit_execution_summary": {},
        "lot_exit_execution_summary": {},
        "lifecycle_snapshot": {"status": "pass"},
        "discipline_summary": {},
        "discipline_adherence": {},
        "final_battle_plan": {"status": "pass", "decision": "ok", "must_do": [], "buy_candidates": [], "blocked_candidates": []},
    }
    monkeypatch.setattr(cli, "load_ohlcv_dataset", lambda *a, **k: pd.read_csv(csv_path))
    monkeypatch.setattr(cli, "_premarket_context_from_args", lambda *a, **k: context)
    monkeypatch.setattr(cli, "_render_premarket_report_from_context", lambda _context: "# premarket")
    monkeypatch.setattr(cli, "_trade_records_from_args", lambda _args: [])
    monkeypatch.setattr(cli, "_trade_plan_records_from_args", lambda _args: [])
    monkeypatch.setattr(cli, "_execution_confirmation_records_from_args", lambda _args: [])

    cli.run_workflow_trading_day(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["cockpit"]["status"] == "pass"
    assert payload["timeline"]["status"] == "pass"
    assert payload["state"]["status"] == "pass"
    assert payload["assistant"]["status"] == "pass"
    assert payload["daily_brief"]["status"] == "pass"
    assert payload["daily_brief"]["can_open_new_position"] is False
    assert payload["trade_plan_batch"]["status"] == "pass"
    assert payload["trade_plan_batch"]["persisted_count"] == 0
    assert payload["review_doctor"]["status"] == "pass"
    assert payload["review_attribution"]["status"] == "pass"
    assert payload["attribution_policy"]["status"] == "pass"
    for key in ["premarket_report", "battle_plan", "cockpit", "execution_audit", "lifecycle", "timeline", "assistant", "daily_brief", "trade_plan_batch", "review_doctor", "review_attribution", "attribution_policy"]:
        assert Path(payload["outputs"][key]).exists()
    assert Path(args.state_log).exists()
    assert Path(args.trade_plan_batch_output).exists()
    assert "# 今日交易主清单" in Path(args.daily_output).read_text(encoding="utf-8")
    assert Path(args.review_doctor_output).exists()
    assert "# 复盘归因" in Path(args.review_attribution_output).read_text(encoding="utf-8")
    assert "# Attribution Policy" in Path(args.attribution_policy_output).read_text(encoding="utf-8")


def test_workflow_execution_gate_blocks_on_pretrade_block():
    gate = cli._workflow_execution_gate(
        {"status": "ok"},
        {"status": "ok"},
        {
            "market_temperature": {"regime": "warm"},
            "pretrade_checks": [{"status": "block"}],
            "holding_risk": {"status": "pass"},
        },
    )

    assert gate["status"] == "block"
    assert "禁止新开仓" in gate["message"]
    assert gate["pretrade_counts"]["block"] == 1


def test_workflow_execution_gate_blocks_on_final_battle_plan():
    gate = cli._workflow_execution_gate(
        {"status": "ok"},
        {"status": "ok"},
        {
            "market_temperature": {"regime": "warm"},
            "pretrade_checks": [{"status": "pass"}],
            "holding_risk": {"status": "pass"},
            "final_battle_plan": {
                "status": "block",
                "reasons": ["strategy gate blocks new positions"],
            },
        },
    )

    assert gate["status"] == "block"
    assert gate["battle_plan_status"] == "block"
    assert any("battle_plan:" in item for item in gate["reasons"])
