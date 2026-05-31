from quant_system.reports.strategy_portfolio import render_strategy_portfolio_lines


def test_render_strategy_portfolio_lines_shows_sleeve_budget_and_status():
    lines = render_strategy_portfolio_lines(
        {
            "name": "adaptive_strategy_portfolio",
            "market_temperature": {"regime": "warm", "score": 62},
            "sleeves": [
                {
                    "name": "strong_stock_screen",
                    "role": "main_attack",
                    "status": "active",
                    "budget_pct": 0.42,
                    "selected_count": 4,
                    "reason": "active in warm",
                },
                {
                    "name": "trend_breakout",
                    "role": "probe",
                    "status": "skipped",
                    "budget_pct": 0,
                    "selected_count": 0,
                    "reason": "no budget",
                },
            ],
        }
    )
    text = "\n".join(lines)

    assert "adaptive_strategy_portfolio" in text
    assert "strong_stock_screen" in text
    assert "42.0%" in text
    assert "trend_breakout" in text


def test_render_strategy_portfolio_lines_handles_disabled_manager():
    assert render_strategy_portfolio_lines(None) == ["- 未启用策略组合管理器。"]
