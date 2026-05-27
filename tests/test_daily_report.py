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
        )
    )

    assert "000001 平安银行" in content
    assert "20日动量 12.00%" in content
    assert "注意回撤" in content
