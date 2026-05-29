from quant_system.reports.strategy_health import render_strategy_health_lines


def test_render_strategy_health_lines_handles_empty():
    assert render_strategy_health_lines(None) == ["- 暂无策略健康度数据。"]


def test_render_strategy_health_lines_renders_table_and_leader():
    lines = render_strategy_health_lines(
        [
            {
                "strategy": "dragon",
                "score": 82.5,
                "status": "strong",
                "action": "pause",
                "selection_count": 12,
                "trade_count": 8,
                "promotion_count": 2,
                "alert_level": "block",
                "alerts": ["execution_deviation", "mistake_cluster"],
                "constraint_policy": {"note": "最近 2 日触发 2 次阻断，进入冷静期：暂停新增仓位。"},
                "constraint_policy_config": {
                    "window_days": 5,
                    "cooldown_block_count": 2,
                    "warn_escalation_count": 2,
                    "recover_after_clean_days": 3,
                },
                "avg_execution_deviation_pct": 0.01,
                "trade_plan_match_rate": 0.75,
                "trade_plan_unmatched_count": 1,
                "trade_plan_orphan_count": 2,
                "trade_plan_avg_price_deviation_pct": 0.04,
                "lifecycle_pressure": {"status": "warn", "score": 82, "action": "reduce"},
                "top_mistake": "追高",
                "top_tag": "计划内",
            }
        ]
    )

    content = "\n".join(lines)
    assert "| 策略 | 评分 | 状态 | 动作 | 告警 | 选股 | 交易 | 晋级 | 偏差 | 计划压力 | 生命周期 | 错误 |" in content
    assert "dragon" in content
    assert "强势" in content
    assert "暂停策略" in content
    assert "阻断" in content
    assert "当前优先跟踪" in content
    assert "追高" in content
    assert "计划压力" in content
    assert "命中率 75.0%" in content
    assert "失配 1" in content
    assert "孤儿成交 2" in content
    assert "生命周期压力" in content


def test_render_strategy_health_lines_uses_trade_plan_pressure_summary():
    lines = render_strategy_health_lines(
        [
            {
                "strategy": "dragon",
                "score": 82.5,
                "status": "strong",
                "action": "pause",
                "selection_count": 12,
                "trade_count": 8,
                "promotion_count": 2,
                "alert_level": "block",
                "alerts": ["execution_deviation", "mistake_cluster"],
                "trade_plan_audit": {"match_rate": 0.75, "unmatched_plans": 1, "orphan_trades": 2, "score": 80},
            }
        ]
    )

    content = "\n".join(lines)
    assert "计划压力" in content
    assert "命中率 75.0%" in content
    assert "失配 1" in content
    assert "孤儿成交 2" in content
