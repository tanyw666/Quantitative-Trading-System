from pathlib import Path

from quant_system.portfolio.journal import TradeJournal, TradeJournalEntry, summarize_trade_journal


def test_trade_journal_records_execution_deviation(tmp_path: Path):
    journal = TradeJournal(tmp_path / "trades.jsonl")
    journal.add(
        TradeJournalEntry(
            date="2024-01-01",
            symbol="000001",
            side="BUY",
            price=10.5,
            quantity=100,
            reason="突破买入",
            planned_price=10.0,
            tags=["计划内"],
        )
    )

    records = journal.list()

    assert records[0]["amount"] == 1050.0
    assert abs(records[0]["execution_deviation_pct"] - 0.05) < 1e-12


def test_summarize_trade_journal_counts_tags_and_mistakes():
    records = [
        {
            "side": "BUY",
            "amount": 1000,
            "execution_deviation_pct": 0.02,
            "tags": ["追高"],
            "mistake_type": "追高",
        },
        {
            "side": "SELL",
            "amount": 1100,
            "execution_deviation_pct": -0.01,
            "tags": ["止盈"],
            "mistake_type": "",
        },
    ]

    summary = summarize_trade_journal(records)

    assert summary["total_trades"] == 2
    assert summary["buy_count"] == 1
    assert summary["sell_count"] == 1
    assert summary["mistake_counts"]["追高"] == 1
    assert summary["tag_counts"]["止盈"] == 1
