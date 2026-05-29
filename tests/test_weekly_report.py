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
            promotion_summary={
                "total": 2,
                "ok_count": 2,
                "failed_count": 0,
                "backtest_count": 2,
                "latest_created_at": "2026-05-28T08:48:17+00:00",
                "best_backtest": {
                    "output": "configs/strategies/promoted.yaml",
                    "total_return": 0.08,
                    "sharpe": 1.5,
                    "trades": 4,
                },
                "records": [
                    {
                        "created_at": "2026-05-28T08:48:17+00:00",
                        "output": "configs/strategies/promoted.yaml",
                        "ok": True,
                        "total_return": 0.08,
                        "sharpe": 1.5,
                    }
                ],
            },
            strategy_health=[
                {
                    "strategy": "strong_stock_screen",
                    "score": 74,
                    "status": "watch",
                    "action": "keep",
                    "selection_count": 8,
                    "trade_count": 3,
                    "promotion_count": 2,
                    "trade_plan_match_rate": 0.8,
                    "trade_plan_unmatched_count": 1,
                    "trade_plan_orphan_count": 0,
                    "trade_plan_avg_price_deviation_pct": 0.04,
                }
            ],
            strategy_rotation=[
                {
                    "strategy": "strong_stock_screen",
                    "rotation_score": 72,
                    "priority": "观察",
                    "action": "只做计划内确认单",
                    "recent_warn_count": 1,
                    "recent_block_count": 0,
                    "reasons": ["存在预警"],
                }
            ],
            rotation_history={
                "snapshot_count": 2,
                "first_created_at": "2026-05-28T09:00:00+00:00",
                "latest_created_at": "2026-05-29T09:00:00+00:00",
                "strategies": [
                    {"strategy": "strong_stock_screen", "latest_rotation_score": 72, "trend": "flat", "main_count": 0, "pause_count": 0, "avg_rotation_score": 70}
                ],
            },
            constraint_summary={
                "total": 2,
                "warn_count": 1,
                "block_count": 1,
                "by_strategy": {"strong_stock_screen": 2},
                "by_alert": {"execution_deviation": 1, "mistake_cluster": 1},
                "latest_created_at": "2026-05-29T09:10:00+00:00",
                "records": [
                    {
                        "created_at": "2026-05-29T09:10:00+00:00",
                        "source": "portfolio.allocate",
                        "strategy": "strong_stock_screen",
                        "alert_level": "warn",
                        "action": "reduce",
                        "alerts": ["execution_deviation"],
                    }
                ],
            },
            trade_stats={
                "total_trades": 1,
                "buy_count": 1,
                "sell_count": 0,
                "total_amount": 1000,
                "avg_execution_deviation_pct": 0.01,
                "mistake_counts": {"追高": 1},
                "tag_counts": {"计划内": 1},
                "gate_counts": {"warn": 1},
                "gate_violation_count": 1,
            },
            notes=[],
            action_execution_summary={
                "actionable_count": 2,
                "executed_count": 1,
                "partial_count": 1,
                "missed_count": 0,
                "execution_rate": 0.5,
                "avg_delay_days": 1.0,
                "avg_price_deviation_pct": 0.02,
                "records": [{"action_date": "2026-05-29", "symbol": "000001", "action": "reduce", "execution_status": "partial", "required_quantity": 500, "executed_quantity": 200, "delay_days": 1}],
            },
        )
    )

    assert "市场温度" in content
    assert "今日策略总览" in content
    assert "3日" in content
    assert "按进场闸门" in content
    assert "策略实验" in content
    assert "策略晋升" in content
    assert "统一摘要" in content
    assert "策略健康" in content
    assert "策略轮换建议" in content
    assert "策略轮换建议" in content
    assert "执行偏差过大" in content
    assert "strong_stock_screen" in content
    assert "持仓动作执行审计" in content
    assert "promoted.yaml" in content
    assert "balanced" in content
    assert "min_20d_return=0.12" in content
    assert "pass" in content
    assert "追高" in content
    assert "盘前门禁" in content
    assert "预警" in content
    assert "预警/阻断状态下买入" in content


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


def test_default_weekly_notes_mentions_gate_violations():
    notes = default_weekly_notes([], {"gate_violation_count": 1})

    assert any("盘前门禁" in note for note in notes)


def test_weekly_report_reflects_trade_plan_pressure_in_rotation():
    content = WeeklyReport().render(
        WeeklyReportInput(
            title="周报",
            market_temperature={"score": 60, "regime": "warm", "stance": "适度进攻", "advance_ratio": 0.5, "above_ma20_ratio": 0.6},
            selection_summary=[],
            gate_summary=[],
            experiment_summary={"preferred_horizon": 3, "min_count": 5, "result_count": 1, "recommendation": None},
            promotion_summary={"total": 0},
            strategy_rotation=[
                {
                    "strategy": "dragon",
                    "rotation_score": 41,
                    "priority": "暂停",
                    "action": "暂停新开仓，只复盘和处理持仓",
                    "recent_warn_count": 1,
                    "recent_block_count": 1,
                    "reasons": ["计划-成交失配严重"],
                }
            ],
            trade_stats={},
            notes=[],
            trade_plan_audit={
                "total_plans": 2,
                "matched_trades": 1,
                "unmatched_plans": 1,
                "orphan_trades": 0,
                "match_rate": 0.5,
                "avg_price_deviation_pct": 0.06,
            },
        )
    )

    assert "计划-成交" in content
    assert "失配严重" in content or "失配" in content


def test_weekly_report_renders_next_week_action_advice():
    content = WeeklyReport().render(
        WeeklyReportInput(
            title="周报",
            market_temperature={"score": 60, "regime": "warm", "stance": "适度进攻", "advance_ratio": 0.5, "above_ma20_ratio": 0.6},
            selection_summary=[],
            gate_summary=[],
            experiment_summary={"preferred_horizon": 3, "min_count": 5, "result_count": 1, "recommendation": None},
            promotion_summary={"total": 0},
            strategy_health=[
                {
                    "strategy": "dragon",
                    "score": 74,
                    "status": "watch",
                    "action": "keep",
                    "selection_count": 8,
                    "trade_count": 3,
                    "promotion_count": 2,
                    "trade_plan_audit": {"match_rate": 0.5, "unmatched_plans": 1, "orphan_trades": 1, "score": 81},
                }
            ],
            constraint_summary={"records": []},
            trade_stats={},
            notes=[],
            trade_plan_audit={"match_rate": 0.5, "unmatched_plans": 1, "orphan_trades": 1},
        )
    )

    assert "下周动作建议" in content
    assert "计划压力" in content
