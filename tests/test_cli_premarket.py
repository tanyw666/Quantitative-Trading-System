from argparse import Namespace

import quant_system.cli as cli


def test_premarket_cli_runs(tmp_path, capsys):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2024-01-01,000001,10,11,9,10,1000\n"
        "2024-01-02,000001,10,12,9,11,1000\n",
        encoding="utf-8",
    )
    args = Namespace(
        csv=csv_path,
        cache_dir=tmp_path / "cache",
        universe=None,
        strategy="strong_stock_screen",
        config=None,
        settings=None,
        tracker=tmp_path / "selections.jsonl",
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
        output=tmp_path / "premarket.md",
    )

    cli.run_premarket_report(args)

    output = capsys.readouterr().out
    assert "premarket.md" in output
    assert args.output.exists()


def test_premarket_cli_can_record_discipline(tmp_path, capsys):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2024-01-01,000001,10,11,9,10,1000\n"
        "2024-01-02,000001,10,12,9,11,1000\n",
        encoding="utf-8",
    )
    journal_path = tmp_path / "trades.jsonl"
    journal_path.write_text(
        '{"date":"2024-01-02","symbol":"000001","side":"BUY","price":10,"quantity":100,"amount":1000,"gate_status":"warn","gate_reasons":["pretrade_warn"]}\n',
        encoding="utf-8",
    )
    discipline_log = tmp_path / "discipline.jsonl"
    args = Namespace(
        csv=csv_path,
        cache_dir=tmp_path / "cache",
        universe=None,
        strategy="strong_stock_screen",
        config=None,
        settings=None,
        tracker=tmp_path / "selections.jsonl",
        journal=journal_path,
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
        output=tmp_path / "premarket.md",
        record_discipline=True,
        discipline_log=discipline_log,
    )

    cli.run_premarket_report(args)

    assert "premarket.md" in capsys.readouterr().out
    assert discipline_log.exists()
    assert '"status": "warn"' in discipline_log.read_text(encoding="utf-8")
