from quant_system.reports.strategy_rotation import build_strategy_rotation, render_strategy_rotation_lines


def test_build_strategy_rotation_prioritizes_healthy_strategy_and_penalizes_blocks():
    rotation = build_strategy_rotation(
        [
            {
                "strategy": "dragon",
                "score": 82,
                "action": "increase",
                "alert_level": "pass",
                "policy_state": "normal",
            },
            {
                "strategy": "reversal",
                "score": 78,
                "action": "pause",
                "alert_level": "block",
                "policy_state": "blocked",
                "alerts": ["mistake_cluster"],
            },
        ],
        {
            "records": [
                {"strategy": "reversal", "alert_level": "block", "alerts": ["mistake_cluster"]},
                {"strategy": "reversal", "alert_level": "warn", "alerts": ["execution_deviation"]},
            ]
        },
        {"best_backtest": {"output": "configs/strategies/dragon.yaml"}},
    )

    assert rotation[0]["strategy"] == "dragon"
    assert rotation[0]["priority"] == "主打"
    assert rotation[1]["priority"] == "暂停"
    assert rotation[1]["recent_block_count"] == 1


def test_render_strategy_rotation_lines_renders_table_and_leader():
    lines = render_strategy_rotation_lines(
        [
            {
                "strategy": "dragon",
                "rotation_score": 90,
                "priority": "主打",
                "action": "作为下个交易日主策略",
                "recent_warn_count": 0,
                "recent_block_count": 0,
                "reasons": ["健康度建议提高优先级"],
            }
        ]
    )
    content = "\n".join(lines)

    assert "| 策略 | 轮换分 | 优先级 | 动作 | 预警 | 阻断 | 依据 |" in content
    assert "当前主线建议：dragon" in content


def test_build_strategy_rotation_penalizes_trade_plan_mismatch():
    rotation = build_strategy_rotation(
        [
            {
                "strategy": "dragon",
                "score": 84,
                "action": "increase",
                "alert_level": "pass",
                "policy_state": "normal",
                "trade_plan_match_rate": 0.62,
                "trade_plan_unmatched_count": 3,
                "trade_plan_orphan_count": 2,
                "trade_plan_avg_price_deviation_pct": 0.05,
            },
            {
                "strategy": "reversal",
                "score": 76,
                "action": "keep",
                "alert_level": "pass",
                "policy_state": "normal",
            },
        ],
        {},
        {},
    )

    assert rotation[0]["strategy"] == "reversal"
    assert rotation[-1]["strategy"] == "dragon"
    assert "计划-成交失配严重" in rotation[-1]["reasons"]


def test_render_strategy_rotation_lines_mentions_trade_plan_pressure():
    lines = render_strategy_rotation_lines(
        [
            {
                "strategy": "dragon",
                "rotation_score": 88,
                "priority": "主打",
                "action": "作为下个交易日主策略",
                "recent_warn_count": 0,
                "recent_block_count": 0,
                "trade_plan_audit": {"match_rate": 0.72, "unmatched_plans": 2, "orphan_trades": 1},
                "reasons": ["计划压力：命中率 72.0%，失配 2，孤儿成交 1"],
            }
        ]
    )

    content = "\n".join(lines)
    assert "计划压力" in content
    assert "命中率 72.0%" in content


def test_render_strategy_rotation_lines_mentions_lifecycle_pressure():
    lines = render_strategy_rotation_lines(
        [
            {
                "strategy": "dragon",
                "rotation_score": 70,
                "priority": "观察",
                "action": "只做计划内确认单",
                "recent_warn_count": 1,
                "recent_block_count": 0,
                "lifecycle_pressure": {"summary": "状态 warn；动作执行 50.0%"},
                "reasons": ["生命周期闭环降档"],
            }
        ]
    )

    content = "\n".join(lines)
    assert "生命周期压力" in content
    assert "动作执行 50.0%" in content
