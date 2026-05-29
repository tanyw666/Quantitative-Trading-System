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

    assert "策略 | 轮换分" in content
    assert "当前主线建议：dragon" in content
