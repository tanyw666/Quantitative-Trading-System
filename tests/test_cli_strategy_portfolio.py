import json

import pandas as pd

import quant_system.cli as cli


def _write_prices(path):
    dates = pd.date_range("2024-01-01", periods=70)
    closes = [10 + index * 0.18 for index in range(70)]
    pd.DataFrame(
        {
            "date": dates,
            "symbol": ["000001"] * len(dates),
            "open": [value - 0.05 for value in closes],
            "high": [value + 0.25 for value in closes],
            "low": [value - 0.25 for value in closes],
            "close": closes,
            "volume": [1000] * 69 + [2600],
            "turnover": [2.0] * len(dates),
        }
    ).to_csv(path, index=False)


def test_screen_accepts_strategy_portfolio_config_and_outputs_annotated_candidates(tmp_path, capsys):
    csv_path = tmp_path / "prices.csv"
    portfolio_path = tmp_path / "portfolio.yaml"
    _write_prices(csv_path)
    portfolio_path.write_text(
        """
name: cli_portfolio
max_position_pct: 0.2
sleeves:
  - name: attack
    strategy: strong_stock_screen
    role: main_attack
    enabled_regimes: [warm, hot, neutral, cold]
    budget_pct_by_regime:
      warm: 0.4
      hot: 0.4
      neutral: 0.2
      cold: 0.1
    params:
      min_20d_return: 0.05
      min_volume_ratio: 1.0
      max_volume_ratio: 5.0
      max_atr_pct: 0.5
      max_close_ma20_gap: 1.0
      min_entry_structure_score: 0.0
      max_chase_risk_score: 100.0
      max_candle_warning_count: 5
      block_false_breakout: false
""".strip()
        + "\n",
        encoding="utf-8",
    )
    args = cli.build_parser().parse_args(
        [
            "screen",
            "--csv",
            str(csv_path),
            "--portfolio-config",
            str(portfolio_path),
            "--top",
            "3",
            "--journal",
            str(tmp_path / "trades.jsonl"),
            "--promotion-log",
            str(tmp_path / "promotions.jsonl"),
            "--constraint-log",
            str(tmp_path / "constraints.jsonl"),
            "--approval-log",
            str(tmp_path / "approvals.jsonl"),
        ]
    )

    cli.run_screen(args)

    rows = json.loads(capsys.readouterr().out)
    assert rows
    assert rows[0]["source_strategy"] == "attack"
    assert rows[0]["strategy_role"] == "main_attack"
    assert rows[0]["position_cap_pct"] <= 0.2


def test_workflow_accepts_strategy_portfolio_config_arg():
    args = cli.build_parser().parse_args(
        [
            "workflow",
            "premarket",
            "--csv",
            "prices.csv",
            "--portfolio-config",
            "configs/strategy_portfolio.yaml",
        ]
    )

    assert args.portfolio_config.name == "strategy_portfolio.yaml"


def test_optimize_portfolio_calibration_accepts_args():
    args = cli.build_parser().parse_args(
        [
            "optimize",
            "portfolio-calibration",
            "--csv",
            "prices.csv",
            "--portfolio-config",
            "configs/strategy_portfolio.yaml",
            "--preset",
            "compact",
            "--format",
            "markdown",
        ]
    )

    assert args.optimize_command == "portfolio-calibration"
    assert args.preset == "compact"
    assert args.format == "markdown"
