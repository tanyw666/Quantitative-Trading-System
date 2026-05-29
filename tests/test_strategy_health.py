from quant_system.optimizer.health import summarize_strategy_health


def test_summarize_strategy_health_combines_selection_trade_and_promotion_records():
    health = summarize_strategy_health(
        selections=[
            {"date": "2026-05-28", "strategy": "dragon", "symbol": "000001", "close": 10},
            {"date": "2026-05-29", "strategy": "dragon", "symbol": "000002", "close": 12},
        ],
        trades=[
            {
                "date": "2026-05-29",
                "strategy": "dragon",
                "symbol": "000001",
                "side": "BUY",
                "amount": 1000,
                "tags": ["计划内"],
            },
            {
                "date": "2026-05-30",
                "strategy": "dragon",
                "symbol": "000001",
                "side": "SELL",
                "amount": 1200,
                "execution_deviation_pct": 0.02,
                "mistake_type": "追高",
                "tags": ["止盈"],
            },
        ],
        promotions=[
            {
                "created_at": "2026-05-29T09:00:00+00:00",
                "strategy_name": "dragon",
                "ok": True,
                "backtest": {"total_return": 0.1},
            }
        ],
    )

    assert len(health) == 1
    assert health[0].strategy == "dragon"
    assert health[0].selection_count == 2
    assert health[0].trade_count == 2
    assert health[0].promotion_count == 1
    assert health[0].promotion_success_rate == 1.0
    assert health[0].win_rate == 1.0
    assert health[0].gross_buy_amount == 1000
    assert health[0].gross_sell_amount == 1200
    assert health[0].avg_execution_deviation_pct == 0.02
    assert health[0].mistake_count == 1
    assert health[0].top_mistake == "追高"
    assert health[0].top_tag in {"计划内", "止盈"}
    assert health[0].alert_level == "warn"
    assert "behavior_mistake" in health[0].alerts
    assert health[0].status == "strong"
    assert health[0].action == "keep"


def test_summarize_strategy_health_keeps_weak_strategy_visible():
    health = summarize_strategy_health(
        selections=[],
        trades=[
            {
                "date": "2026-05-29",
                "strategy": "reversal",
                "symbol": "000001",
                "side": "BUY",
                "amount": 5000,
            }
        ],
        promotions=[],
    )

    assert health[0].strategy == "reversal"
    assert health[0].status == "weak"
    assert health[0].action == "reduce"
    assert health[0].alert_level == "pass"


def test_summarize_strategy_health_penalizes_large_execution_deviation_and_mistakes():
    health = summarize_strategy_health(
        selections=[{"date": "2026-05-29", "strategy": "swing", "symbol": "000001", "close": 10}],
        trades=[
            {
                "date": "2026-05-29",
                "strategy": "swing",
                "symbol": "000001",
                "side": "BUY",
                "amount": 10000,
                "execution_deviation_pct": 0.08,
                "mistake_type": "追高",
                "tags": ["情绪单"],
            },
            {
                "date": "2026-05-30",
                "strategy": "swing",
                "symbol": "000001",
                "side": "SELL",
                "amount": 9800,
                "execution_deviation_pct": -0.06,
                "mistake_type": "不止损",
                "tags": ["情绪单"],
            },
        ],
        promotions=[],
    )

    assert abs((health[0].avg_execution_deviation_pct or 0.0) - 0.01) < 1e-12
    assert health[0].mistake_count == 2
    assert health[0].top_tag == "情绪单"
    assert health[0].alert_level == "block"
    assert health[0].action == "pause"
    assert "emotion_tag" in health[0].alerts
    assert health[0].score < 65
