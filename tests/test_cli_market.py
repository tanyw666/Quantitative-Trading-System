from argparse import Namespace

import quant_system.cli as cli


def test_market_temperature_cli_uses_sector_top_and_runs(tmp_path, capsys):
    args = Namespace(
        csv=tmp_path / "sample.csv",
        cache_dir=tmp_path / "cache",
        universe=None,
        strategy="strong_stock_screen",
        config=None,
        settings=None,
        top=None,
        sector_column=None,
        sector_top=5,
        only_top_sectors=False,
    )
    args.csv.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2024-01-01,000001,10,11,9,10,1000\n"
        "2024-01-02,000001,10,12,9,11,1000\n"
        "2024-01-01,000002,20,21,19,20,1000\n"
        "2024-01-02,000002,20,20,18,19,1000\n",
        encoding="utf-8",
    )

    cli.run_market_temperature(args)

    output = capsys.readouterr().out
    assert '"regime"' in output
    assert '"score"' in output
