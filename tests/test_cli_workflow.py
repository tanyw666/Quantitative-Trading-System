from argparse import Namespace
import json

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
        ]
    )

    assert args.workflow_command == "premarket"
    assert args.refresh_cache is True
    assert args.refresh_start == "20240101"


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
    assert report_path.exists()
    assert summary_path.exists()
    assert args.discipline_log.exists()


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
