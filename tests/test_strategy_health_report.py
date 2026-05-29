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
                "constraint_policy": {"note": "近5日触发 2 次阻断，进入冷静期：暂停新增仓位。"},
                "constraint_policy_config": {
                    "window_days": 5,
                    "cooldown_block_count": 2,
                    "warn_escalation_count": 2,
                    "recover_after_clean_days": 3,
                },
                "avg_execution_deviation_pct": 0.01,
                "top_mistake": "追高",
                "top_tag": "计划内",
            }
        ]
    )

    content = "\n".join(lines)
    assert "| 策略 | 评分 | 状态 | 动作 | 告警 | 选股 | 交易 | 晋级 | 偏差 | 错误 |" in content
    assert "dragon" in content
    assert "强势" in content
    assert "暂停策略" in content
    assert "阻断" in content
    assert "当前优先跟踪" in content
    assert "追高" in content
    assert "最近交易标签重心：计划内" in content
    assert "当前告警：执行偏差过大、错误集中" in content
    assert "执行状态：近5日触发 2 次阻断" in content
    assert "风控模板" in content
    assert "观察窗5日" in content
