from quant_system.reports.weekly import WeeklyReport, WeeklyReportInput, default_weekly_notes


def test_weekly_report_renders_selection_and_trade_stats():
    content = WeeklyReport().render(
        WeeklyReportInput(
            title="周报",
            market_temperature={"score": 60, "regime": "warm", "stance": "适度进攻", "advance_ratio": 0.5, "above_ma20_ratio": 0.6},
            selection_summary=[{"horizon": 3, "count": 2, "mean_return": 0.05, "win_rate": 0.5}],
            gate_summary=[{"entry_gate": "pass", "horizon": 3, "count": 1, "mean_return": 0.1, "win_rate": 1.0}],
            experiment_summary={
                "preferred_horizon": 3,
                "min_count": 5,
                "result_count": 2,
                "recommendation": {
                    "name": "balanced",
                    "strategy": "strong_stock_screen",
                    "params": {"min_20d_return": 0.12},
                    "mean_return": 0.03,
                    "win_rate": 0.6,
                    "count": 5,
                    "score": 0.0315,
                },
            },
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
    assert "策略实验" in content
    assert "balanced" in content
    assert "min_20d_return=0.12" in content
    assert "pass" in content
    assert "追高" in content


def test_weekly_report_renders_empty_experiment_summary():
    content = WeeklyReport().render(
        WeeklyReportInput(
            title="周报",
            market_temperature=None,
            selection_summary=[],
            gate_summary=[],
            experiment_summary={"preferred_horizon": 3, "min_count": 5, "result_count": 1, "recommendation": None},
            trade_stats={},
            notes=[],
        )
    )

    assert "暂无满足门槛的推荐参数组" in content


def test_default_weekly_notes_mentions_mistakes():
    notes = default_weekly_notes([], {"mistake_counts": {"追高": 2}})

    assert notes
