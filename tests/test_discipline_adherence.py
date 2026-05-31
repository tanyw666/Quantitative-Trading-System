from quant_system.portfolio.discipline_adherence import evaluate_discipline_adherence


def test_discipline_adherence_flags_same_day_buy_after_block():
    summary = evaluate_discipline_adherence(
        [
            {
                "date": "2026-05-29",
                "source": "report.premarket",
                "status": "block",
                "advice": ["No new positions"],
                "target_exposure_pct": 0,
                "allocated_pct": 0.2,
            }
        ],
        [
            {
                "date": "2026-05-29",
                "symbol": "000001",
                "side": "BUY",
                "amount": 1000,
                "gate_status": "block",
            }
        ],
        limit=10,
    )

    assert summary["total"] == 1
    assert summary["block_count"] == 1
    assert summary["violation_count"] == 1
    assert summary["records"][0]["violations"] == ["new_buy_after_block", "new_buy_under_zero_exposure"]


def test_discipline_adherence_flags_missing_gate_snapshot_next_day():
    summary = evaluate_discipline_adherence(
        [
            {
                "date": "2026-05-29",
                "source": "report.daily",
                "status": "warn",
                "advice": ["Some trades have no gate snapshot; attach workflow summary or manual gate fields when recording trades."],
                "missing_gate_count": 2,
            }
        ],
        [
            {
                "date": "2026-05-30",
                "symbol": "000002",
                "side": "BUY",
                "amount": 2000,
                "gate_status": "",
                "workflow_summary": "",
            }
        ],
        limit=10,
    )

    assert summary["warn_count"] == 1
    assert summary["by_violation"]["missing_gate_snapshot_after_advice"] == 1
    assert summary["records"][0]["applicable_start"] == "2026-05-30"


def test_discipline_adherence_passes_when_warn_followed_by_clean_buy():
    summary = evaluate_discipline_adherence(
        [
            {
                "date": "2026-05-29",
                "source": "report.daily",
                "status": "warn",
                "advice": ["Review every BUY executed under warn/block status."],
            }
        ],
        [
            {
                "date": "2026-05-30",
                "symbol": "000003",
                "side": "BUY",
                "amount": 3000,
                "gate_status": "pass",
                "workflow_summary": "reports/workflow.json",
            }
        ],
        limit=10,
    )

    assert summary["pass_count"] == 1
    assert summary["adherence_rate"] == 1.0
    assert summary["records"][0]["violations"] == []


def test_discipline_adherence_treats_documented_exception_as_non_violation():
    summary = evaluate_discipline_adherence(
        [
            {
                "date": "2026-05-29",
                "source": "report.premarket",
                "status": "block",
                "advice": ["No new positions"],
            }
        ],
        [
            {
                "date": "2026-05-29",
                "symbol": "000004",
                "side": "BUY",
                "amount": 4000,
                "gate_status": "block",
                "discipline_exception": True,
                "exception_reason": "approved gap-fill exception",
            }
        ],
        limit=10,
    )

    assert summary["pass_count"] == 1
    assert summary["exception_count"] == 1
    assert summary["records"][0]["approved_exception_count"] == 1
    assert summary["records"][0]["violations"] == []


def test_discipline_adherence_flags_unexplained_exception():
    summary = evaluate_discipline_adherence(
        [
            {
                "date": "2026-05-29",
                "source": "report.premarket",
                "status": "block",
                "advice": ["No new positions"],
            }
        ],
        [
            {
                "date": "2026-05-29",
                "symbol": "000005",
                "side": "BUY",
                "amount": 5000,
                "gate_status": "block",
                "discipline_exception": True,
                "exception_reason": "",
            }
        ],
        limit=10,
    )

    assert summary["block_count"] == 1
    assert summary["by_violation"]["unexplained_discipline_exception"] == 1


def test_discipline_adherence_flags_buy_during_structure_cooldown():
    summary = evaluate_discipline_adherence(
        [
            {
                "date": "2026-05-29",
                "source": "report.daily",
                "status": "block",
                "structure_violation_count": 2,
                "advice": ["Structure rule: 2 BUY records hit structure-gate warnings; next session blocks chase/false-breakout entries until a clean pretrade is regenerated."],
            }
        ],
        [
            {
                "date": "2026-05-30",
                "symbol": "000006",
                "side": "BUY",
                "amount": 6000,
                "gate_status": "pass",
                "workflow_summary": "reports/workflow.json",
            }
        ],
        limit=10,
    )

    assert summary["block_count"] == 1
    assert summary["by_violation"]["structure_cooldown_buy"] == 1
