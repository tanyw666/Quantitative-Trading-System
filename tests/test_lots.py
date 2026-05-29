from argparse import Namespace
import json

import quant_system.cli as cli
from quant_system.portfolio.lots import build_lot_book, render_lot_book_lines


def test_build_lot_book_tracks_open_and_closed_lots():
    records = [
        {"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100},
        {"date": "2026-05-03", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 12, "quantity": 100},
        {"date": "2026-05-05", "symbol": "000001", "name": "Demo", "side": "SELL", "price": 13, "quantity": 100, "reason": "tp"},
    ]

    book = build_lot_book(records, prices={"000001": 14}, as_of="2026-05-10")

    payload = book.to_dict()
    assert payload["total_open_lots"] == 1
    assert payload["total_closed_lots"] == 1
    assert payload["open_lots"][0]["entry_price"] == 12
    assert payload["closed_lots"][0]["realized_pnl"] == 300
    assert payload["summary"]["realized_win_count"] == 1


def test_build_lot_book_marks_stale_open_lot():
    records = [{"date": "2026-04-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100}]

    book = build_lot_book(records, prices={"000001": 9.5}, as_of="2026-05-05")

    payload = book.to_dict()
    assert payload["open_lots"][0]["age_bucket"] == "stale"
    assert payload["summary"]["stale_open_lot_count"] == 1


def test_render_lot_book_lines_shows_lots():
    records = [{"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100}]
    book = build_lot_book(records, prices={"000001": 11}, as_of="2026-05-05")

    lines = render_lot_book_lines(book)

    assert any("Open lots" in line for line in lines)
    assert any("000001" in line for line in lines)


def test_portfolio_lots_cli_records_snapshot(tmp_path, capsys):
    journal = tmp_path / "trades.jsonl"
    log = tmp_path / "lot_books.jsonl"
    journal.write_text(
        json.dumps({"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100}) + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal,
        sqlite=None,
        price=["000001=11"],
        as_of="2026-05-05",
        format="json",
        output=None,
        log=log,
        record=True,
    )

    cli.run_portfolio_lots(args)

    output = capsys.readouterr().out
    saved = json.loads(log.read_text(encoding="utf-8").strip())
    assert '"total_open_lots": 1' in output
    assert saved["total_open_lots"] == 1


def test_review_lot_stats_cli_outputs_markdown(tmp_path, capsys):
    journal = tmp_path / "trades.jsonl"
    journal.write_text(
        json.dumps({"date": "2026-05-01", "symbol": "000001", "name": "Demo", "side": "BUY", "price": 10, "quantity": 100}) + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        journal=journal,
        sqlite=None,
        price=["000001=11"],
        as_of="2026-05-05",
        format="markdown",
        output=None,
    )

    cli.run_review_lot_stats(args)

    output = capsys.readouterr().out
    assert "Lot Lifecycle" in output
    assert "000001" in output
