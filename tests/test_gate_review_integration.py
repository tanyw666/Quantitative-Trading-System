from quant_system.reports.briefing import BriefingInput, BriefingReport
from quant_system.reports.daily import DailyReport, DailyReportInput
from quant_system.reports.premarket import PremarketReport, PremarketReportInput
from quant_system.reports.weekly import WeeklyReport, WeeklyReportInput


GATE_REVIEW = {
    "total_trades": 2,
    "gate_record_count": 2,
    "missing_gate_count": 0,
    "status_counts": {"pass": 1, "warn": 1},
    "buy_status_counts": {"pass": 1, "warn": 1},
    "violation_count": 1,
    "violation_rate": 0.5,
    "by_reason": {"pretrade_warn": 1},
    "action_items": ["Review every BUY executed under warn/block status."],
}


def test_daily_report_embeds_gate_review():
    content = DailyReport().render(
        DailyReportInput(
            title="Daily",
            market_view="warm",
            selected=[],
            risks=[],
            gate_review=GATE_REVIEW,
            trade_stats={"avg_execution_deviation_pct": 0.03},
            discipline_adherence={"total": 1, "adherence_rate": 1.0, "pass_count": 1, "warn_count": 0, "block_count": 0, "violation_count": 0, "by_violation": {}, "records": []},
        )
    )

    assert "Gate Discipline" in content
    assert "BUY violation rate" in content
    assert "Discipline Advice" in content
    assert "Discipline Adherence" in content


def test_weekly_report_embeds_gate_review():
    content = WeeklyReport().render(
        WeeklyReportInput(
            title="Weekly",
            market_temperature=None,
            selection_summary=[],
            trade_stats={},
            notes=[],
            gate_review=GATE_REVIEW,
            discipline_adherence={"total": 1, "adherence_rate": 0.0, "pass_count": 0, "warn_count": 1, "block_count": 0, "violation_count": 1, "by_violation": {"warn_block_buy_after_warn": 1}, "records": []},
        )
    )

    assert "Gate Discipline" in content
    assert "pretrade_warn" in content
    assert "Discipline Advice" in content
    assert "Discipline Adherence" in content


def test_briefing_report_embeds_gate_review():
    content = BriefingReport().render(
        BriefingInput(
            title="Briefing",
            market_temperature={"score": 50, "regime": "warm", "stance": "watch", "advance_ratio": 0.5, "above_ma20_ratio": 0.5},
            candidates=[],
            allocation_plan={"target_exposure_pct": 0, "allocated_pct": 0, "items": []},
            position_book={"total_market_value": 0, "total_unrealized_pnl": 0, "total_exposure_pct": 0, "positions": []},
            holding_risk={"status": "pass", "checks": []},
            gate_review=GATE_REVIEW,
            trade_stats={"avg_execution_deviation_pct": 0.03},
            discipline_adherence={"total": 1, "adherence_rate": 1.0, "pass_count": 1, "warn_count": 0, "block_count": 0, "violation_count": 0, "by_violation": {}, "records": []},
        )
    )

    assert "Gate Discipline" in content
    assert "Warn/block BUY count" in content
    assert "Discipline Advice" in content
    assert "Discipline Adherence" in content


def test_premarket_report_embeds_gate_review():
    content = PremarketReport().render(
        PremarketReportInput(
            title="Premarket",
            market_temperature={"score": 50, "regime": "warm", "stance": "watch", "advance_ratio": 0.5, "above_ma20_ratio": 0.5},
            market_context=None,
            data_health=None,
            candidates=[],
            allocation_plan={"target_exposure_pct": 0, "allocated_pct": 0, "items": []},
            pretrade_checks=[],
            position_book={"total_market_value": 0, "total_unrealized_pnl": 0, "total_exposure_pct": 0, "positions": []},
            holding_risk={"status": "pass", "checks": []},
            gate_review=GATE_REVIEW,
            trade_stats={"avg_execution_deviation_pct": 0.03},
            discipline_adherence={"total": 1, "adherence_rate": 1.0, "pass_count": 1, "warn_count": 0, "block_count": 0, "violation_count": 0, "by_violation": {}, "records": []},
        )
    )

    assert "Gate Discipline" in content
    assert "BUY violation rate" in content
    assert "Discipline Advice" in content
    assert "Discipline Adherence" in content
