import json

import pandas as pd

import quant_system.cli as cli


def test_run_portfolio_tradable_writes_json(monkeypatch, tmp_path):
    output = tmp_path / "tradable.json"
    csv_path = tmp_path / "prices.csv"
    pd.DataFrame(
        {
            "date": ["2026-05-29", "2026-05-30"],
            "symbol": ["000001", "000001"],
            "open": [10, 10.1],
            "high": [10.5, 10.6],
            "low": [9.8, 10.0],
            "close": [10.0, 10.2],
            "volume": [100000, 120000],
        }
    ).to_csv(csv_path, index=False)
    args = cli.build_parser().parse_args(
        [
            "portfolio",
            "tradable",
            "--csv",
            str(csv_path),
            "--symbol",
            "000001",
            "--current-price",
            "10.2",
            "--planned-pct",
            "0.05",
            "--stop-price",
            "9.7",
            "--target-price",
            "12",
            "--as-of",
            "2026-05-30",
            "--output",
            str(output),
        ]
    )
    monkeypatch.setattr(cli, "_current_strategy_health", lambda _args: None)

    cli.run_portfolio_tradable(args)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["symbol"] == "000001"
    assert payload["status"] in {"pass", "warn", "block"}
    assert any(check["name"] == "data_staleness" for check in payload["checks"])


def test_run_portfolio_tradable_can_render_markdown(monkeypatch, tmp_path):
    output = tmp_path / "tradable.md"
    csv_path = tmp_path / "prices.csv"
    pd.DataFrame(
        {
            "date": ["2026-05-30"],
            "symbol": ["000001"],
            "open": [10],
            "high": [10.5],
            "low": [9.8],
            "close": [10],
            "volume": [100000],
        }
    ).to_csv(csv_path, index=False)
    args = cli.build_parser().parse_args(
        [
            "portfolio",
            "tradable",
            "--csv",
            str(csv_path),
            "--symbol",
            "000001",
            "--current-price",
            "10.99",
            "--planned-pct",
            "0.05",
            "--format",
            "markdown",
            "--output",
            str(output),
            "--as-of",
            "2026-05-30",
        ]
    )
    monkeypatch.setattr(cli, "_current_strategy_health", lambda _args: None)

    cli.run_portfolio_tradable(args)

    content = output.read_text(encoding="utf-8")
    assert "# Tradability Check" in content
    assert "limit_state" in content
