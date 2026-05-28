from quant_system.reports.daily import DailyReport, DailyReportInput


def test_daily_report_renders_selected_metrics():
    content = DailyReport().render(
        DailyReportInput(
            title="日报",
            market_view="市场偏强",
            selected=[
                {
                    "symbol": "000001",
                    "name": "平安银行",
                    "close": 12.3,
                    "momentum_20": 0.12,
                    "volume_ratio_20": 1.8,
                    "reason": "强势突破",
                }
            ],
            risks=["注意回撤"],
            experiment_summary={
                "preferred_horizon": 1,
                "min_count": 5,
                "result_count": 2,
                "recommendation": {
                    "name": "gap_hi_0.03_lo_-0.01",
                    "strategy": "dragon_leader",
                    "params": {"max_next_open_gap": 0.03},
                    "mean_return": 0.02,
                    "win_rate": 0.6,
                    "score": 0.05,
                },
            },
            promotion_summary={
                "total": 1,
                "ok_count": 1,
                "failed_count": 0,
                "backtest_count": 1,
                "latest_created_at": "2026-05-28T08:48:17+00:00",
                "best_backtest": {
                    "output": "configs/strategies/promoted.yaml",
                    "total_return": 0.05,
                    "sharpe": 1.2,
                    "trades": 3,
                },
                "records": [
                    {
                        "created_at": "2026-05-28T08:48:17+00:00",
                        "output": "configs/strategies/promoted.yaml",
                        "ok": True,
                        "total_return": 0.05,
                        "sharpe": 1.2,
                    }
                ],
            },
        )
    )

    assert "000001 平安银行" in content
    assert "20日动量 12.00%" in content
    assert "策略参数参考" in content
    assert "策略晋升" in content
    assert "promoted.yaml" in content
    assert "gap_hi_0.03_lo_-0.01" in content
    assert "平均收益：2.00%" in content
    assert "注意回撤" in content


def test_daily_report_renders_empty_experiment_summary():
    content = DailyReport().render(
        DailyReportInput(
            title="日报",
            market_view="市场震荡",
            selected=[],
            risks=[],
            experiment_summary={"preferred_horizon": 3, "min_count": 5, "result_count": 1, "recommendation": None},
        )
    )

    assert "暂无满足门槛的推荐参数组" in content
