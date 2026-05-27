from quant_system.reports.dragon import DragonValidationInput, DragonValidationReport


def test_dragon_validation_report_renders_signal_and_backtest_tracks():
    content = DragonValidationReport().render(
        DragonValidationInput(
            title="龙头战法验证",
            entry_gate="pass",
            entry_model="next-open",
            buy_price="open",
            signal_summary=[{"horizon": 3, "count": 2, "mean_return": 0.05, "win_rate": 0.5}],
            gate_summary=[{"entry_gate": "pass", "horizon": 3, "count": 2, "mean_return": 0.05, "win_rate": 0.5}],
            backtest_summary={"total_return": 0.01, "final_equity": 101000, "max_drawdown": 0.02, "trades": 1, "win_rate": 1.0},
        )
    )

    assert "信号后验" in content
    assert "按进场闸门" in content
    assert "可成交回测" in content
    assert "pass" in content
    assert "next-open" in content
    assert "open" in content
