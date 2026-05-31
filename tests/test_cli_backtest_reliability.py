from argparse import Namespace

import pandas as pd

import quant_system.cli as cli


def write_prices(path):
    dates = pd.date_range("2024-01-01", periods=35)
    closes = [10 + index * 0.2 for index in range(len(dates))]
    pd.DataFrame(
        {
            "date": dates,
            "symbol": ["000001"] * len(dates),
            "open": closes,
            "high": [value + 0.1 for value in closes],
            "low": [value - 0.1 for value in closes],
            "close": closes,
            "volume": [1000] * len(dates),
        }
    ).to_csv(path, index=False)


def test_optimize_backtest_reliability_cli_outputs_json(tmp_path, capsys):
    csv_path = tmp_path / "prices.csv"
    write_prices(csv_path)
    args = Namespace(
        csv=csv_path,
        strategy=["strong_stock_screen"],
        config=[],
        cash=10000,
        buy_price="open",
        execution_timing="next_bar",
        train_ratio=0.7,
        regime_lookback=5,
        bull_threshold=0.02,
        bear_threshold=-0.02,
        min_rows_per_symbol=10,
        max_stale_days=None,
        as_of=None,
        format="json",
        output=None,
    )

    cli.run_optimize_backtest_reliability(args)

    output = capsys.readouterr().out
    assert '"ranking"' in output
    assert '"strong_stock_screen"' in output
    assert '"consistency"' in output


def test_optimize_backtest_reliability_cli_writes_markdown(tmp_path, capsys):
    csv_path = tmp_path / "prices.csv"
    output_path = tmp_path / "reliability.md"
    write_prices(csv_path)
    args = Namespace(
        csv=csv_path,
        strategy=["strong_stock_screen"],
        config=[],
        cash=10000,
        buy_price="open",
        execution_timing="next_bar",
        train_ratio=0.7,
        regime_lookback=5,
        bull_threshold=0.02,
        bear_threshold=-0.02,
        min_rows_per_symbol=10,
        max_stale_days=None,
        as_of=None,
        format="markdown",
        output=output_path,
    )

    cli.run_optimize_backtest_reliability(args)

    assert str(output_path) in capsys.readouterr().out
    assert "回测可信度审计" in output_path.read_text(encoding="utf-8")
