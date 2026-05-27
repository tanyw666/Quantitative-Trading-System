from quant_system.reports.weekly import WeeklyReport, WeeklyReportInput, default_weekly_notes


def test_weekly_report_renders_selection_and_trade_stats():
    content = WeeklyReport().render(
        WeeklyReportInput(
            title="周报",
            market_temperature={"score": 60, "regime": "warm", "stance": "适度进攻", "advance_ratio": 0.5, "above_ma20_ratio": 0.6},
            selection_summary=[{"horizon": 3, "count": 2, "mean_return": 0.05, "win_rate": 0.5}],
            gate_summary=[{"entry_gate": "pass", "horizon": 3, "count": 1, "mean_return": 0.1, "win_rate": 1.0}],
            trade_stats={
                "total_trades": 1,
                "buy_count": 1,
                "sell_count": 0,
                "total_amount": 1000,
                "avg_execution_deviation_pct": 0.01,
                "mistake_counts": {"追高": 1},
                "tag_counts": {"计划内": 1},
            },
            notes=[],
        )
    )

    assert "市场温度" in content
    assert "3日" in content
    assert "按进场闸门" in content
    assert "pass" in content
    assert "追高" in content


def test_default_weekly_notes_mentions_mistakes():
    notes = default_weekly_notes([], {"mistake_counts": {"追高": 2}})

    assert notes
