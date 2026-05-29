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

    assert "Tomorrow gate rule" in content
    assert "Logging rule" in content
    assert "Execution rule" in content
    assert "Exception rule" in content
    assert "Mistake focus" in content
    assert "Holding rule" in content
    assert "Exposure rule" in content


def test_discipline_advice_has_clean_default():
    lines = render_discipline_advice_lines()

    assert lines == ["- Discipline rule: no critical discipline issue detected; keep precheck, gate snapshot, and trade journal complete."]


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
