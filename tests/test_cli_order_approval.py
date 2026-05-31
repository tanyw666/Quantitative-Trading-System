from types import SimpleNamespace

import pandas as pd

import quant_system.cli as cli


class DemoStrategy:
    def screen(self, frame):
        return pd.DataFrame(
            {
                "symbol": ["000001"],
                "name": ["Demo"],
                "score": [90],
                "risk_grade": ["medium"],
                "close": [10.0],
            }
        )


def test_run_portfolio_approve_writes_markdown(monkeypatch, tmp_path):
    output = tmp_path / "approval.md"
    approval_log = tmp_path / "order_approvals.jsonl"
    assistant = tmp_path / "assistant.json"
    assistant.write_text('{"status":"warn","urgent_actions":[{"text":"Wait for liquidity after open."}]}', encoding="utf-8")

    args = cli.build_parser().parse_args(
        [
            "portfolio",
            "approve",
            "--csv",
            "prices.csv",
            "--symbol",
            "000001",
            "--current-price",
            "10",
            "--planned-pct",
            "0.1",
            "--assistant-json",
            str(assistant),
            "--record",
            "--log",
            str(approval_log),
            "--format",
            "markdown",
            "--output",
            str(output),
        ]
    )
    monkeypatch.setattr(
        cli,
        "load_ohlcv_dataset",
        lambda *a, **k: pd.DataFrame(
            {"date": ["2026-05-30"], "symbol": ["000001"], "open": [10], "high": [10.4], "low": [9.9], "close": [10], "volume": [100000]}
        ),
    )
    monkeypatch.setattr(cli, "strategy_from_args", lambda _args: DemoStrategy())
    monkeypatch.setattr(
        cli,
        "settings_from_args",
        lambda _args: SimpleNamespace(
            scoring=SimpleNamespace(weights={}),
            risk=SimpleNamespace(regime_exposure=None, cap_by_risk=None),
        ),
    )
    monkeypatch.setattr(cli, "enrich_and_score_candidates", lambda _frame, candidates, *_args, **_kwargs: candidates)
    monkeypatch.setattr(
        cli,
        "calculate_market_temperature",
        lambda *_args, **_kwargs: SimpleNamespace(to_dict=lambda: {"regime": "warm", "stance": "test"}),
    )
    monkeypatch.setattr(cli, "_current_strategy_health", lambda _args: {"strategy": "demo", "alert_level": "pass", "action": "keep"})

    cli.run_portfolio_approve(args)

    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "# Order Approval" in content
    assert "Status: warn" in content
    assert approval_log.exists()
    assert '"symbol": "000001"' in approval_log.read_text(encoding="utf-8")


def test_run_review_approvals_reads_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    cli.SQLiteStore(sqlite_path).insert_order_approval(
        {
            "created_at": "2026-05-30T10:00:00+08:00",
            "symbol": "000001",
            "status": "warn",
            "decision": "WARN",
            "confirmed_pct": 0.05,
            "confirmed_value": 5000,
            "suggested_quantity": 500,
            "evidence": {"assistant_status": "warn"},
            "reasons": ["assistant: warn"],
            "action_items": ["Reduce size."],
        }
    )
    args = cli.build_parser().parse_args(
        [
            "review",
            "approvals",
            "--sqlite",
            str(sqlite_path),
            "--status",
            "warn",
        ]
    )

    cli.run_review_approvals(args)

    out = capsys.readouterr().out
    assert '"warn_count": 1' in out
    assert '"000001": 1' in out
