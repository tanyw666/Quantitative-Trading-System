from quant_system.reports.briefing import BriefingInput, BriefingReport, action_notes, candidate_dragon_note


def test_briefing_report_renders_core_sections():
    content = BriefingReport().render(
        BriefingInput(
            title="简报",
            market_temperature={"score": 70, "regime": "warm", "stance": "适度进攻", "advance_ratio": 0.5, "above_ma20_ratio": 0.6},
            candidates=[{"symbol": "000001", "name": "Demo", "score": 90, "risk_grade": "medium", "close": 10}],
            allocation_plan={
                "target_exposure_pct": 0.3,
                "allocated_pct": 0.12,
                "strategy_adjustment_note": "dragon_leader 策略健康度预警，目标总仓位由 60.0% 下调至 30.0%。触发：execution_deviation",
                "items": [],
            },
            position_book={"total_market_value": 1000, "total_unrealized_pnl": 100, "total_exposure_pct": 0.1, "positions": []},
            lot_book={"total_open_lots": 1, "total_closed_lots": 1, "open_market_value": 1000, "open_unrealized_pnl": 100, "realized_pnl": 200, "summary": {"realized_win_rate": 1.0}, "open_lots": [{"lot_id": "000001-1", "symbol": "000001", "entry_date": "2026-05-20", "remaining_quantity": 1000, "entry_price": 9.0, "market_price": 10.0, "unrealized_pnl": 100.0, "holding_days": 9}], "action_items": ["Largest open lot is 000001."]},
            holding_risk={"status": "pass", "checks": []},
            holding_action_plan={
                "status": "warn",
                "exit_count": 0,
                "reduce_count": 1,
                "watch_count": 1,
                "hold_count": 0,
                "actions": [
                    {"symbol": "000001", "action": "reduce", "status": "warn", "current_quantity": 1000, "target_quantity": 800, "reason": "单票超限"},
                ],
                "action_items": ["执行减仓动作"],
            },
            dragon_candidates=[
                {
                    "symbol": "600162",
                    "name": "香江控股",
                    "dragon_score": 148,
                    "seal_quality_score": 100,
                    "entry_gate": "pass",
                    "dragon_state": "sealed",
                    "dragon_tags": "reseal-candidate,high-acceptance",
                }
            ],
            sectors=[{"sector": "银行", "strength_score": 80, "candidate_count": 1, "avg_momentum_20": 0.1}],
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
                "latest_created_at": "2026-05-28T09:00:55+00:00",
                "best_backtest": {
                    "output": "configs/strategies/promoted.yaml",
                    "total_return": 0.05,
                    "sharpe": 1.2,
                    "trades": 3,
                },
                "records": [
                    {
                        "created_at": "2026-05-28T09:00:55+00:00",
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
                }
            ],
            strategy_rotation=[
                {
                    "strategy": "dragon_leader",
                    "rotation_score": 40,
                    "priority": "暂停",
                    "action": "暂停新开仓，只复盘和处理持仓",
                    "recent_warn_count": 0,
                    "recent_block_count": 1,
                    "reasons": ["存在阻断"],
                }
            ],
            rotation_history={
                "snapshot_count": 2,
                "first_created_at": "2026-05-28T09:00:00+00:00",
                "latest_created_at": "2026-05-29T09:00:00+00:00",
                "strategies": [
                    {"strategy": "dragon_leader", "latest_rotation_score": 40, "trend": "down", "main_count": 0, "pause_count": 2, "avg_rotation_score": 45}
                ],
            },
            constraint_summary={
                "total": 1,
                "warn_count": 0,
                "block_count": 1,
                "by_strategy": {"dragon_leader": 1},
                "by_alert": {"mistake_cluster": 1},
                "latest_created_at": "2026-05-29T09:10:00+00:00",
                "records": [
                    {
                        "created_at": "2026-05-29T09:10:00+00:00",
                        "source": "portfolio.precheck",
                        "strategy": "dragon_leader",
                        "alert_level": "block",
                        "action": "pause",
                        "alerts": ["mistake_cluster"],
                    }
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
            action_execution_summary={
                "actionable_count": 1,
                "executed_count": 0,
                "partial_count": 0,
                "missed_count": 1,
                "execution_rate": 0.0,
                "avg_delay_days": 0.0,
                "avg_price_deviation_pct": 0.0,
                "records": [{"action_date": "2026-05-29", "symbol": "000001", "action": "reduce", "execution_status": "missed", "required_quantity": 200, "executed_quantity": 0, "delay_days": None}],
            },
            data_health={
                "status": "ok",
                "rows": 1000,
                "symbols": 50,
                "start_date": "2024-01-01",
                "end_date": "2026-05-29",
                "issues": [],
            },
            pretrade_checks=[
                {
                    "symbol": "000001",
                    "status": "warn",
                    "planned_pct": 0.1,
                    "entry_price": 10,
                    "stop_price": 9,
                    "reward_risk": 1.2,
                    "candidate_snapshot": {"name": "Demo"},
                    "checks": [{"name": "reward_risk", "status": "warn", "message": "盈亏比偏低"}],
                }
            ],
        )
    )

    assert "计划压力" in content
    assert "命中率 50.0%" in content
    assert "计划失配偏多" in content or "计划压力" in content
    assert "今日动作" in content
    assert "持仓动作计划" in content
    assert "持仓动作执行审计" in content
    assert "Lot Lifecycle" in content
    assert "单票超限" in content


def test_briefing_report_renders_empty_experiment_summary():
    content = BriefingReport().render(
        BriefingInput(
            title="简报",
            market_temperature={"score": 50, "regime": "warm", "stance": "观察", "advance_ratio": 0.5, "above_ma20_ratio": 0.5},
            candidates=[],
            allocation_plan={"target_exposure_pct": 0, "allocated_pct": 0, "items": []},
            position_book={"total_market_value": 0, "total_unrealized_pnl": 0, "total_exposure_pct": 0, "positions": []},
            holding_risk={"status": "pass", "checks": []},
            experiment_summary={"preferred_horizon": 3, "min_count": 5, "result_count": 1, "recommendation": None},
            promotion_summary={"total": 0},
        )
    )

    assert "暂无满足门槛的推荐参数组" in content
    assert "暂无可优先观察的策略" in content


def test_action_notes_prioritizes_blocking_risk():
    notes = action_notes({"regime": "warm"}, [{"symbol": "000001"}], {"status": "block"})

    assert "暂停新增仓位" in notes[0]


def test_candidate_dragon_note_renders_dragon_context():
    note = candidate_dragon_note(
        {
            "dragon_score": 110,
            "seal_quality_score": 95,
            "dragon_state": "repair",
            "entry_gate": "watch",
            "dragon_tags": "reseal-candidate,failed-limit-repair",
        }
    )

    assert "dragon 110.0" in note
    assert "seal 95.0" in note
    assert "gate watch" in note
    assert "failed-limit-repair" in note
