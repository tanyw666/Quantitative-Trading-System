from pathlib import Path

from quant_system.portfolio.journal import (
    TradeJournal,
    TradeJournalEntry,
    summarize_discipline_exceptions,
    summarize_gate_journal,
    summarize_trade_journal,
)
from quant_system.storage.sqlite_store import SQLiteStore


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
            gate_status="warn",
            gate_message="只允许计划内确认单",
            gate_reasons=["数据健康存在预警"],
            workflow_summary="reports/premarket_workflow.json",
            discipline_exception=True,
            exception_reason="planned exception",
        )
    )

    records = journal.list()

    assert records[0]["amount"] == 1050.0
    assert abs(records[0]["execution_deviation_pct"] - 0.05) < 1e-12
    assert records[0]["gate_status"] == "warn"
    assert records[0]["gate_reasons"] == ["数据健康存在预警"]
    assert records[0]["discipline_exception"] is True
    assert records[0]["exception_reason"] == "planned exception"


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
            "discipline_exception": True,
        },
    ]

    summary = summarize_trade_journal(records)

    assert summary["total_trades"] == 2
    assert summary["buy_count"] == 1
    assert summary["sell_count"] == 1
    assert summary["mistake_counts"]["追高"] == 1
    assert summary["tag_counts"]["止盈"] == 1
    assert summary["gate_counts"] == {}
    assert summary["gate_violation_count"] == 0
    assert summary["discipline_exception_count"] == 1


def test_summarize_trade_journal_counts_gate_violations():
    records = [
        {"side": "BUY", "amount": 1000, "gate_status": "warn", "tags": ["gate-warn"]},
        {"side": "SELL", "amount": 1000, "gate_status": "block", "tags": []},
    ]

    summary = summarize_trade_journal(records)

    assert summary["gate_counts"]["warn"] == 1
    assert summary["gate_counts"]["block"] == 1
    assert summary["gate_violation_count"] == 1


def test_summarize_trade_journal_counts_emotion_tags():
    records = [
        {"side": "BUY", "amount": 1000, "emotion_tag": "greed", "tags": []},
        {"side": "BUY", "amount": 1000, "tags": ["emotion:fear"]},
    ]

    summary = summarize_trade_journal(records)

    assert summary["emotion_counts"] == {"greed": 1, "fear": 1}
    assert summary["emotional_trade_count"] == 2


def test_summarize_gate_journal_builds_discipline_panel():
    records = [
        {
            "date": "2026-05-28",
            "symbol": "000001",
            "side": "BUY",
            "strategy": "strong_stock_screen",
            "amount": 1000,
            "gate_status": "pass",
            "gate_reasons": [],
        },
        {
            "date": "2026-05-29",
            "symbol": "000002",
            "side": "BUY",
            "strategy": "strong_stock_screen",
            "amount": 1200,
            "gate_status": "block",
            "gate_message": "no new buys",
            "gate_reasons": ["data_health_failed"],
        },
        {"date": "2026-05-29", "symbol": "000003", "side": "SELL", "amount": 800},
    ]

    summary = summarize_gate_journal(records, limit=10)

    assert summary["total_trades"] == 3
    assert summary["gate_record_count"] == 2
    assert summary["missing_gate_count"] == 1
    assert summary["status_counts"]["pass"] == 1
    assert summary["status_counts"]["block"] == 1
    assert summary["buy_status_counts"]["block"] == 1
    assert summary["violation_count"] == 1
    assert summary["violation_rate"] == 0.5
    assert summary["by_reason"]["data_health_failed"] == 1
    assert summary["latest_violations"][0]["symbol"] == "000002"
    assert summary["action_items"]


def test_summarize_gate_journal_counts_structure_gate_violations():
    records = [
        {
            "date": "2026-05-29",
            "symbol": "000001",
            "side": "BUY",
            "strategy": "strong_stock_screen",
            "amount": 1000,
            "gate_status": "warn",
            "gate_message": "Chase-risk score is elevated.",
            "gate_reasons": ["chase_risk"],
        },
        {
            "date": "2026-05-29",
            "symbol": "000002",
            "side": "BUY",
            "strategy": "trend_breakout",
            "amount": 1200,
            "gate_status": "block",
            "gate_message": "False-breakout flag is active.",
            "gate_reasons": ["false_breakout"],
        },
    ]

    summary = summarize_gate_journal(records, limit=10)

    assert summary["structure_violation_count"] == 2
    assert summary["by_structure_reason"]["chase_risk"] == 1
    assert summary["by_structure_reason"]["false_breakout"] == 1
    assert any("Structure-gate violations" in item for item in summary["action_items"])


def test_summarize_discipline_exceptions_requires_reasons():
    records = [
        {
            "date": "2026-05-29",
            "symbol": "000001",
            "side": "BUY",
            "strategy": "dragon",
            "amount": 1000,
            "discipline_exception": True,
            "exception_reason": "approved gap exception",
        },
        {
            "date": "2026-05-30",
            "symbol": "000002",
            "side": "BUY",
            "strategy": "dragon",
            "amount": 2000,
            "gate_status": "block",
            "gate_reasons": ["forced-gate-block"],
            "discipline_exception": True,
            "exception_reason": "",
        },
    ]

    summary = summarize_discipline_exceptions(records, limit=10)

    assert summary["exception_count"] == 2
    assert summary["approved_exception_count"] == 1
    assert summary["missing_reason_count"] == 1
    assert summary["by_strategy"]["dragon"] == 2
    assert summary["latest_missing_reason"][0]["symbol"] == "000002"
    assert "gate:block" in summary["latest_missing_reason"][0]["exception_sources"]
    assert summary["action_items"]


def test_trade_journal_dual_writes_sqlite(tmp_path: Path):
    sqlite_path = tmp_path / "quant.sqlite"
    journal = TradeJournal(tmp_path / "trades.jsonl", sqlite_path=sqlite_path)
    journal.add(
        TradeJournalEntry(
            date="2024-01-02",
            symbol="000001",
            side="BUY",
            price=11.0,
            quantity=200,
            reason="test",
            tags=["swing"],
            gate_status="block",
            gate_message="禁止新开仓",
            gate_reasons=["数据健康失败"],
            workflow_summary="reports/premarket_workflow.json",
            discipline_exception=True,
            exception_reason="manual override after plan review",
        )
    )

    records = journal.list()
    trades = SQLiteStore(sqlite_path).read_trades(symbol="000001")

    assert records[0]["symbol"] == "000001"
    assert len(trades) == 1
    assert trades.loc[0, "quantity"] == 200
    assert trades.loc[0, "gate_status"] == "block"
    assert "数据健康失败" in trades.loc[0, "gate_reasons_json"]
    assert trades.loc[0, "discipline_exception"] == 1
    assert trades.loc[0, "exception_reason"] == "manual override after plan review"
