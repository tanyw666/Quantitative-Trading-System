from quant_system.reports.review_doctor import build_review_doctor_report, render_review_doctor_markdown


def test_build_review_doctor_report_flags_missing_plan_and_stale_snapshot():
    report = build_review_doctor_report(
        selections=[{"date": "2026-05-28"}],
        trades=[{"date": "2026-05-30", "side": "BUY"}],
        trade_plans=[],
        action_plans=[{"action_date": "2026-05-29", "status": "warn"}],
        exit_plans=[{"plan_date": "2026-05-29", "sell_all_count": 1}],
        lifecycle_snapshots=[{"snapshot_date": "2026-05-29", "status": "block"}],
        trading_day_states=[{"date": "2026-05-29", "status": "block"}],
    )

    names = {item["name"] for item in report["issues"]}
    assert report["status"] == "warn"
    assert "missing_trade_plans" in names
    assert "missing_execution_confirmations" in names
    assert "stale_lifecycle_snapshot" in names
    assert "latest_lifecycle_blocked" in names
    assert "latest_exit_sell_all" in names
    assert "stale_trading_day_state" in names
    assert "latest_trading_day_blocked" in names


def test_render_review_doctor_markdown_outputs_sections():
    content = render_review_doctor_markdown(
        {
            "status": "warn",
            "counts": {
                "selections": 1,
            "trades": 2,
            "trade_plans": 1,
            "execution_confirmations": 1,
            "action_plans": 1,
                "exit_plans": 1,
                "lifecycle_snapshots": 1,
                "trading_day_states": 1,
            },
            "latest": {
                "selection_date": "2026-05-29",
            "trade_date": "2026-05-30",
            "trade_plan_date": "2026-05-29",
            "execution_confirmation_date": "2026-05-30",
            "action_date": "2026-05-29",
                "exit_plan_date": "2026-05-29",
                "lifecycle_date": "2026-05-29",
                "trading_day_state_date": "2026-05-29",
            },
            "latest_lifecycle_status": "block",
            "latest_trading_day_status": "warn",
            "issues": [{"name": "stale_lifecycle_snapshot", "status": "warn", "message": "最新交易日晚于最新生命周期快照。"}],
            "action_items": ["重大交易或盘后复盘后，刷新并持久化生命周期快照。"],
        }
    )

    assert "# 复盘医生" in content
    assert "执行确认" in content
    assert "## 最新记录" in content
    assert "## 问题" in content
