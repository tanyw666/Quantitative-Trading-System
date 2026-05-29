from quant_system.risk.constraint_audit import (
    build_constraint_audit_record,
    persist_constraint_audit,
    read_constraint_audit_records,
    summarize_constraint_audit_records,
)
from quant_system.storage.sqlite_store import SQLiteStore


def test_build_constraint_audit_record_skips_pass():
    assert build_constraint_audit_record("portfolio.allocate", {"alert_level": "pass"}) is None


def test_persist_constraint_audit_dual_writes(tmp_path):
    log_path = tmp_path / "constraints.jsonl"
    sqlite_path = tmp_path / "quant.sqlite"
    record = build_constraint_audit_record(
        "portfolio.precheck",
        {
            "strategy": "dragon",
            "alert_level": "block",
            "action": "pause",
            "alerts": ["mistake_cluster"],
            "note": "暂停",
        },
        symbol="000001",
    )

    persist_constraint_audit(record, log_path=log_path, sqlite_path=sqlite_path)

    jsonl_records = read_constraint_audit_records(log_path)
    sqlite_records = SQLiteStore(sqlite_path).read_strategy_constraints(limit=1)

    assert jsonl_records[0]["strategy"] == "dragon"
    assert jsonl_records[0]["symbol"] == "000001"
    assert sqlite_records.loc[0, "alert_level"] == "block"


def test_summarize_constraint_audit_records_groups_by_strategy_and_alert():
    summary = summarize_constraint_audit_records(
        [
            {
                "created_at": "2026-05-29T09:00:00+00:00",
                "source": "portfolio.allocate",
                "strategy": "dragon",
                "alert_level": "warn",
                "alerts": ["execution_deviation"],
            },
            {
                "created_at": "2026-05-29T09:10:00+00:00",
                "source": "portfolio.precheck",
                "strategy": "dragon",
                "alert_level": "block",
                "alerts": ["mistake_cluster"],
            },
        ],
        limit=10,
    )

    assert summary["total"] == 2
    assert summary["warn_count"] == 1
    assert summary["block_count"] == 1
    assert summary["by_strategy"]["dragon"] == 2
    assert summary["by_alert"]["execution_deviation"] == 1
    assert summary["trend"]["windows"]["5"]["total"] == 2
    assert summary["trend"]["windows"]["5"]["block_count"] == 1
    assert summary["trend"]["windows"]["10"]["top_strategy"] == "dragon"
