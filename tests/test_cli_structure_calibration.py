from argparse import Namespace

import pandas as pd

import quant_system.cli as cli


def _write_prices(path):
    dates = pd.date_range("2024-01-01", periods=35)
    closes = list(range(10, 44)) + [45]
    pd.DataFrame(
        {
            "date": dates,
            "symbol": ["000001"] * len(dates),
            "name": ["Demo"] * len(dates),
            "open": [value - 0.2 for value in closes],
            "high": [value + 0.5 for value in closes],
            "low": [value - 0.5 for value in closes],
            "close": closes,
            "volume": [1000] * 34 + [2500],
        }
    ).to_csv(path, index=False)


def test_optimize_structure_calibration_cli_outputs_json(tmp_path, capsys):
    csv_path = tmp_path / "prices.csv"
    _write_prices(csv_path)
    args = Namespace(
        csv=csv_path,
        cash=100000,
        buy_price="open",
        execution_timing="next_bar",
        min_20d_return=0.1,
        min_volume_ratio=1.2,
        max_volume_ratio=6.0,
        max_atr_pct=0.3,
        min_ma20_slope=0.0,
        max_close_ma20_gap=0.45,
        max_rsi=90.0,
        min_traded_value=0.0,
        format="json",
        output=None,
    )

    cli.run_optimize_structure_calibration(args)

    output = capsys.readouterr().out
    assert '"case_count"' in output
    assert '"sensitivity"' in output
    assert '"min_entry_structure_score"' in output


def test_optimize_structure_calibration_cli_writes_markdown(tmp_path, capsys):
    csv_path = tmp_path / "prices.csv"
    output_path = tmp_path / "calibration.md"
    _write_prices(csv_path)
    args = Namespace(
        csv=csv_path,
        cash=100000,
        buy_price="open",
        execution_timing="next_bar",
        min_20d_return=0.1,
        min_volume_ratio=1.2,
        max_volume_ratio=6.0,
        max_atr_pct=0.3,
        min_ma20_slope=0.0,
        max_close_ma20_gap=0.45,
        max_rsi=90.0,
        min_traded_value=0.0,
        format="markdown",
        output=output_path,
    )

    cli.run_optimize_structure_calibration(args)

    assert str(output_path) in capsys.readouterr().out
    content = output_path.read_text(encoding="utf-8")
    assert "# Structure Parameter Calibration" in content
    assert "Threshold Sensitivity" in content
