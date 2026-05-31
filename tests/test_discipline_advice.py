from quant_system.reports.discipline_advice import render_discipline_advice_lines
from quant_system.portfolio.discipline import (
    build_discipline_record,
    persist_discipline_record,
    read_discipline_records,
    summarize_discipline_records,
)


def test_discipline_advice_blocks_on_gate_violation_and_holding_risk():
    lines = render_discipline_advice_lines(
        gate_review={"violation_count": 2, "missing_gate_count": 1},
        trade_stats={"avg_execution_deviation_pct": 0.035, "mistake_counts": {"chase": 2}, "discipline_exception_count": 1},
        holding_risk={"status": "block"},
        allocation_plan={"target_exposure_pct": 0.3, "allocated_pct": 0.4},
    )
    content = "\n".join(lines)

    assert "明日门禁规则" in content
    assert "记录规则" in content
    assert "执行规则" in content
    assert "例外规则" in content
    assert "错误聚焦" in content
    assert "持仓规则" in content
    assert "暴露规则" in content


def test_discipline_advice_has_clean_default():
    lines = render_discipline_advice_lines()

    assert lines == ["- 纪律规则：当前没有关键纪律问题；继续把 precheck、门禁快照和交易日志记完整。"]


def test_discipline_record_round_trip_jsonl(tmp_path):
    path = tmp_path / "discipline.jsonl"
    record = build_discipline_record(
        source="report.daily",
        gate_review={"violation_count": 1, "missing_gate_count": 0},
        trade_stats={"avg_execution_deviation_pct": 0.03},
        allocation_plan={"target_exposure_pct": 0.3, "allocated_pct": 0.4},
        record_date="2026-05-29",
    )

    persist_discipline_record(record, log_path=path)
    records = read_discipline_records(path)
    summary = summarize_discipline_records(records, limit=10)

    assert records[0]["status"] == "warn"
    assert summary["total"] == 1
    assert summary["warn_count"] == 1
    assert summary["records"][0]["source"] == "report.daily"


def test_discipline_record_blocks_repeated_structure_gate_violations():
    record = build_discipline_record(
        source="report.daily",
        gate_review={
            "violation_count": 2,
            "structure_violation_count": 2,
            "by_structure_reason": {"false_breakout": 1, "chase_risk": 1},
        },
        trade_stats={"discipline_exception_count": 2},
        record_date="2026-05-29",
    )

    assert record["status"] == "block"
    assert record["structure_violation_count"] == 2
    assert record["structure_reason_counts"]["false_breakout"] == 1
    assert any("Structure rule" in item for item in record["advice"])
    assert any("Cooldown rule" in item for item in record["advice"])


def test_discipline_record_warns_on_emotional_trades():
    record = build_discipline_record(
        source="report.daily",
        trade_stats={"emotion_counts": {"greed": 2}, "emotional_trade_count": 2},
        record_date="2026-05-29",
    )

    assert record["status"] == "warn"
    assert record["emotion_counts"] == {"greed": 2}
    assert record["emotional_trade_count"] == 2
    assert any("Emotion rule" in item for item in record["advice"])
