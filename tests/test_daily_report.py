from quant_system.reports.daily import DailyReport, DailyReportInput, render_data_health_lines


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
            strategy_health=[
                {
                    "strategy": "dragon_leader",
                    "score": 82,
                    "status": "strong",
                    "action": "increase",
                    "selection_count": 5,
                    "trade_count": 2,
                    "promotion_count": 1,
                    "trade_plan_match_rate": 0.88,
                    "trade_plan_unmatched_count": 1,
                    "trade_plan_orphan_count": 0,
                    "trade_plan_avg_price_deviation_pct": 0.02,
                }
            ],
            strategy_rotation=[
                {
                    "strategy": "dragon_leader",
                    "rotation_score": 88,
                    "priority": "主打",
                    "action": "作为下个交易日主策略",
                    "recent_warn_count": 0,
                    "recent_block_count": 0,
                    "reasons": ["健康度建议提高优先级"],
                }
            ],
            rotation_history={
                "snapshot_count": 2,
                "first_created_at": "2026-05-28T09:00:00+00:00",
                "latest_created_at": "2026-05-29T09:00:00+00:00",
                "strategies": [
                    {"strategy": "dragon_leader", "latest_rotation_score": 88, "trend": "up", "main_count": 1, "pause_count": 0, "avg_rotation_score": 80}
                ],
            },
            constraint_summary={
                "total": 1,
                "warn_count": 1,
                "block_count": 0,
                "by_strategy": {"dragon_leader": 1},
                "by_alert": {"execution_deviation": 1},
                "latest_created_at": "2026-05-29T09:10:00+00:00",
                "records": [
                    {
                        "created_at": "2026-05-29T09:10:00+00:00",
                        "source": "portfolio.allocate",
                        "strategy": "dragon_leader",
                        "alert_level": "warn",
                        "action": "reduce",
                        "alerts": ["execution_deviation"],
                    }
                ],
            },
            allocation_plan={
                "target_exposure_pct": 0.3,
                "target_exposure_value": 30000,
                "allocated_pct": 0.12,
                "allocated_value": 12000,
                "strategy_adjustment_note": "dragon_leader 策略健康度预警，目标总仓位由 60.0% 下调至 30.0%。触发：execution_deviation",
                "items": [],
            },
            pretrade_checks=[
                {
                    "symbol": "000001",
                    "status": "pass",
                    "planned_pct": 0.1,
                    "entry_price": 12.3,
                    "stop_price": 11.2,
                    "reward_risk": 2.0,
                    "candidate_snapshot": {"name": "平安银行"},
                    "checks": [],
                }
            ],
            action_execution_summary={
                "actionable_count": 1,
                "executed_count": 1,
                "partial_count": 0,
                "missed_count": 0,
                "execution_rate": 1.0,
                "avg_delay_days": 0.0,
                "avg_price_deviation_pct": -0.01,
                "records": [{"action_date": "2026-05-29", "symbol": "000001", "action": "exit", "execution_status": "executed", "required_quantity": 1000, "executed_quantity": 1000, "delay_days": 0}],
            },
        )
    )

    assert "000001 平安银行" in content
    assert "今日策略总览" in content
    assert "20日动量 12.00%" in content
    assert "策略参数参考" in content
    assert "策略晋升" in content
    assert "统一摘要" in content
    assert "策略健康" in content
    assert "dragon_leader" in content
    assert "策略约束复盘" in content
    assert "策略轮换建议" in content
    assert "策略轮换历史" in content
    assert "执行偏差过大" in content
    assert "策略约束" in content
    assert "目标总仓位由 60.0% 下调至 30.0%" in content
    assert "交易前预检预览" in content
    assert "持仓动作执行审计" in content
    assert "明日降半档执行" in content or "明日进入暂停观察" in content
    assert "promoted.yaml" in content
    assert "gap_hi_0.03_lo_-0.01" in content
    assert "总收益 5.00%" in content
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


def test_daily_report_renders_market_context_once():
    content = DailyReport().render(
        DailyReportInput(
            title="日报",
            market_view="市场偏强",
            selected=[],
            risks=[],
            market_context={"summary_lines": ["- 公告提示：title=测试公告", "- 新闻快讯：title=测试新闻"]},
        )
    )

    assert content.count("公告提示：title=测试公告") == 1
    assert content.count("新闻快讯：title=测试新闻") == 1
    assert content.count("## 1.1 真实市场上下文") == 1


def test_daily_report_renders_data_health():
    content = DailyReport().render(
        DailyReportInput(
            title="日报",
            market_view="市场偏强",
            selected=[],
            risks=[],
            data_health={
                "status": "warn",
                "rows": 1000,
                "symbols": 50,
                "start_date": "2024-01-01",
                "end_date": "2026-05-29",
                "issues": [{"name": "staleness", "status": "warn", "message": "2 symbols stale"}],
            },
        )
    )

    assert "## 1.2 数据健康" in content
    assert "股票数：50" in content
    assert "[提示] 2 symbols stale" in content


def test_render_data_health_lines_shows_clean_checks():
    lines = render_data_health_lines(
        {
            "status": "ok",
            "rows": 100,
            "symbols": 2,
            "start_date": "2024-01-01",
            "end_date": "2024-02-01",
            "issues": [{"name": "duplicates", "status": "pass", "message": "ok"}],
        }
    )

    assert any("关键检查" in line for line in lines)


def test_render_data_health_lines_translates_classified_warnings():
    lines = render_data_health_lines(
        {
            "status": "warn",
            "rows": 100,
            "symbols": 2,
            "start_date": "2024-01-01",
            "end_date": "2024-02-01",
            "issues": [
                {
                    "name": "history_length",
                    "status": "warn",
                    "message": "2 recent/new listings have short history: 001001 新股(2)",
                    "details": {
                        "new_listing_count": 2,
                        "backfill_count": 0,
                        "new_listing_samples": [{"symbol": "001001", "name": "新股", "last_date": "2026-05-28"}],
                    },
                },
                {
                    "name": "staleness",
                    "status": "warn",
                    "message": "1 regular symbols look stale: 688121 卓越股份(29d) | 1 ST/special-status symbols stale separately: 000004 *ST国华(32d). As of 2026-05-29; oldest cached date reaches 2026-04-13.",
                    "details": {
                        "regular_stale_count": 1,
                        "special_stale_count": 1,
                        "regular_stale_samples": [{"symbol": "688121", "name": "卓越股份", "last_date": "2026-04-30"}],
                        "special_stale_samples": [{"symbol": "000004", "name": "*ST国华", "last_date": "2026-04-27"}],
                    },
                },
            ],
        }
    )

    joined = "\n".join(lines)
    assert "新股" in joined
    assert "普通股票行情滞后" in joined
    assert "样本：688121 卓越股份(2026-04-30)" in joined
    assert "[提示]" in joined


def test_daily_report_reflects_trade_plan_audit_pressure():
    content = DailyReport().render(
        DailyReportInput(
            title="日报",
            market_view="市场偏强",
            selected=[],
            risks=[],
            trade_plan_summary={
                "total": 2,
                "pass_count": 1,
                "warn_count": 1,
                "block_count": 0,
                "planned_value": 2000,
                "allowed_value": 1800,
                "records": [
                    {"trade_date": "2026-05-29", "symbol": "000001", "gate_status": "pass", "planned_pct": 0.1, "entry_price": 10.0},
                ],
            },
            trade_plan_audit={
                "total_plans": 2,
                "matched_trades": 1,
                "unmatched_plans": 1,
                "orphan_trades": 1,
                "match_rate": 0.5,
                "avg_price_deviation_pct": 0.05,
            },
        )
    )

    assert "交易计划单" in content
    assert "计划-成交审计" in content
    assert "match rate" in content or "命中率" in content
