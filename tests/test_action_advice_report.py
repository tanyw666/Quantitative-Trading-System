from quant_system.reports.action_advice import render_action_advice_lines


def test_render_action_advice_lines_blocks_when_latest_constraint_blocks():
    lines = render_action_advice_lines(
        strategy_health=[{"strategy": "dragon", "score": 80, "action": "increase", "alert_level": "pass"}],
        constraint_summary={
            "records": [
                {
                    "strategy": "dragon",
                    "alert_level": "block",
                    "action": "pause",
                    "alerts": ["mistake_cluster"],
                }
            ]
        },
        allocation_plan={"target_exposure_pct": 0, "allocated_pct": 0},
        market_temperature={"regime": "warm", "stance": "适度进攻"},
    )
    content = "\n".join(lines)

    assert "暂停观察" in content
    assert "错误集中" in content
    assert "目标 0.0%" in content
    assert "precheck" in content


def test_render_action_advice_lines_uses_leader_when_no_constraint():
    lines = render_action_advice_lines(
        strategy_health=[{"strategy": "trend", "score": 72, "action": "keep", "alert_level": "pass"}],
        market_temperature={"regime": "cold", "stance": "观察"},
    )
    content = "\n".join(lines)

    assert "优先跟踪 trend" in content
    assert "市场温度偏低" in content


def test_render_action_advice_lines_includes_policy_note():
    lines = render_action_advice_lines(
        strategy_health=[
            {
                "strategy": "dragon",
                "score": 66,
                "action": "reduce",
                "alert_level": "warn",
                "alerts": ["recovery_probe"],
                "constraint_policy": {"note": "连续3日无新增约束后恢复正常仓位。"},
            }
        ],
    )

    assert "恢复/冷静期规则" in "\n".join(lines)
