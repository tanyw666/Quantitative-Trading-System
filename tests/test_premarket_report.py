from quant_system.reports.premarket import PremarketReport, PremarketReportInput, premarket_decision


def test_premarket_report_renders_execution_first_sections():
    content = PremarketReport().render(
        PremarketReportInput(
            title="盘前作战单",
            market_temperature={"score": 70, "regime": "warm", "stance": "适度进攻", "advance_ratio": 0.5, "above_ma20_ratio": 0.6},
            market_context={"summary_lines": ["- 新闻快讯：测试消息"]},
            data_health={"status": "ok", "rows": 100, "symbols": 2, "start_date": "2024-01-01", "end_date": "2024-02-01", "issues": []},
            candidates=[{"symbol": "000001", "name": "平安银行", "score": 88, "risk_grade": "medium", "close": 12.3}],
            allocation_plan={
                "target_exposure_pct": 0.3,
                "allocated_pct": 0.1,
                "items": [{"symbol": "000001", "name": "平安银行", "target_pct": 0.1, "target_value": 10000, "stop_price": 11.2}],
            },
            pretrade_checks=[
                {
                    "symbol": "000001",
                    "status": "warn",
                    "planned_pct": 0.1,
                    "entry_price": 12.3,
                    "stop_price": 11.2,
                    "reward_risk": 2.0,
                    "candidate_snapshot": {"name": "平安银行"},
                    "checks": [{"name": "entry_price", "status": "warn", "message": "注意追高"}],
                }
            ],
            position_book={"total_market_value": 0, "total_exposure_pct": 0, "total_unrealized_pnl": 0, "positions": []},
            lot_book={"total_open_lots": 1, "total_closed_lots": 0, "open_market_value": 1000, "open_unrealized_pnl": 50, "realized_pnl": 0, "summary": {"realized_win_rate": 0.0}, "open_lots": [{"lot_id": "000001-1", "symbol": "000001", "entry_date": "2026-05-20", "remaining_quantity": 100, "entry_price": 10.0, "market_price": 10.5, "unrealized_pnl": 50.0, "holding_days": 2}], "action_items": []},
            holding_risk={"status": "pass", "checks": []},
            strategy_health=[{"strategy": "strong_stock_screen", "score": 70, "status": "watch", "action": "keep"}],
            constraint_summary={"total": 0, "records": []},
            strategy_rotation=[{"strategy": "strong_stock_screen", "rotation_score": 70, "priority": "观察", "action": "只做确认单", "reasons": []}],
            rotation_history={"snapshot_count": 0, "strategies": []},
            final_battle_plan={
                "status": "warn",
                "decision": "只允许计划内确认单",
                "market_regime": "warm",
                "market_stance": "适度进攻",
                "target_exposure_pct": 0.3,
                "allocated_pct": 0.1,
                "must_do": [{"priority": "P1", "text": "确认价格不过度偏离"}],
                "buy_candidates": [],
                "blocked_candidates": [],
            },
        )
    )

    assert "开盘前结论" in content
    assert "只允许计划内确认单" in content
    assert "数据与市场" in content
    assert "策略与仓位" in content
    assert "最终作战单" in content
    assert "最终门禁：warn" in content
    assert "候选与预检" in content
    assert "Lot Lifecycle" in content
    assert "000001 平安银行" in content
    assert "注意追高" in content


def test_premarket_decision_blocks_on_any_blocking_precheck():
    decision = premarket_decision(
        {"regime": "warm"},
        [{"symbol": "000001", "status": "block"}],
        {"status": "pass"},
    )

    assert "禁止新开仓" in decision


def test_premarket_decision_blocks_on_strategy_allocation_gate():
    decision = premarket_decision(
        {"regime": "warm"},
        [{"symbol": "000001", "status": "pass"}],
        {"status": "pass"},
        {"strategy_action": "pause", "strategy_alert_level": "block"},
    )

    assert "禁止新开仓" in decision
