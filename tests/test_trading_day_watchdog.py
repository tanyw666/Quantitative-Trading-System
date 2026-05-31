from quant_system.portfolio.trading_day_watchdog import build_trading_day_watchdog, render_trading_day_watchdog_markdown


def test_trading_day_watchdog_flags_missing_today_and_repeated_phase():
    records = [
        {
            "date": "2026-05-28",
            "created_at": "2026-05-28T15:30:00+08:00",
            "status": "warn",
            "phases": [{"phase": "intraday", "status": "warn"}],
            "action_items": ["检查确认单"],
        },
        {
            "date": "2026-05-29",
            "created_at": "2026-05-29T15:30:00+08:00",
            "status": "block",
            "phases": [{"phase": "intraday", "status": "block"}],
            "action_items": ["停止新开仓"],
        },
    ]

    report = build_trading_day_watchdog(records, as_of="2026-05-30", repeat_threshold=2, stale_days=0, limit=10)

    assert report["status"] == "block"
    names = {item["name"] for item in report["alerts"]}
    assert "missing_today_state" in names
    assert "stale_state" in names
    assert "repeated_phase_issue" in names
    assert report["phase_issue_counts"]["intraday"] == 2


def test_render_trading_day_watchdog_markdown_outputs_sections():
    content = render_trading_day_watchdog_markdown(
        {
            "status": "warn",
            "as_of": "2026-05-30",
            "latest_date": "2026-05-30",
            "latest_status": "warn",
            "today_record_count": 1,
            "total_records": 3,
            "alerts": [{"severity": "warn", "name": "current_state_warn", "message": "Current trading-day state has warnings.", "phase": "intraday"}],
            "action_items": ["Refresh the trading-day workflow before adding new risk."],
        }
    )

    assert "# Trading Day Watchdog" in content
    assert "## Alerts" in content
    assert "intraday" in content
