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
        trade_plan_audit={"match_rate": 0.62, "unmatched_plans": 3, "orphan_trades": 2},
        allocation_plan={"target_exposure_pct": 0, "allocated_pct": 0},
        market_temperature={"regime": "warm", "stance": "适度进攻"},
    )
    content = "\n".join(lines)

    assert "暂停观察" in content
    assert "错误集中" in content
    assert "目标 0.0%" in content
    assert "precheck" in content
    assert "计划压力" in content
    assert "命中率 62.0%" in content


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
                "trade_plan_audit": {"match_rate": 0.78, "unmatched_plans": 1, "orphan_trades": 0},
            }
        ],
    )

    content = "\n".join(lines)
    assert "恢复/冷静期规则" in content
    assert "计划压力" in content


def test_render_action_advice_lines_includes_lifecycle_pressure():
    lines = render_action_advice_lines(
        strategy_health=[
            {
                "strategy": "dragon",
                "score": 55,
                "action": "pause",
                "alert_level": "block",
                "alerts": ["lifecycle_block"],
                "lifecycle_pressure": {"summary": "状态 block；退出执行 0.0%"},
            }
        ],
    )

    content = "\n".join(lines)
    assert "生命周期压力" in content
    assert "退出执行 0.0%" in content


def test_render_action_advice_lines_includes_review_doctor_status():
    lines = render_action_advice_lines(
        strategy_health=[
            {
                "strategy": "dragon",
                "score": 55,
                "action": "pause",
                "alert_level": "block",
                "alerts": ["review_doctor_warn"],
                "lifecycle_pressure": {
                    "summary": "window 5; lifecycle block 2, warn 1",
                    "doctor_status": "warn",
                    "doctor_issue_count": 3,
                },
            }
        ],
    )

    content = "\n".join(lines)
    assert "复盘账本：预警（3 个问题）" in content


def test_render_action_advice_lines_includes_holding_actions():
    lines = render_action_advice_lines(
        strategy_health=[{"strategy": "trend", "score": 70, "action": "keep", "alert_level": "pass"}],
        holding_action_plan={
            "exit_count": 1,
            "reduce_count": 1,
            "watch_count": 0,
            "actions": [
                {"symbol": "000001", "action": "exit", "reason": "触发止损"},
                {"symbol": "000002", "action": "reduce", "reason": "单票超限"},
            ],
        },
    )

    content = "\n".join(lines)
    assert "持仓动作" in content
    assert "首要处理：000001 exit" in content


def test_apply_constraint_policy_to_health_includes_trade_plan_note():
    health = {
        "strategy": "dragon",
        "alert_level": "pass",
        "action": "keep",
        "alerts": [],
        "trade_plan_audit": {"match_rate": 0.78, "avg_price_deviation_pct": 0.04},
    }

    from quant_system.risk.constraint_policy import apply_constraint_policy_to_health

    adjusted = apply_constraint_policy_to_health(health, [])

    assert adjusted["policy_note"]
    assert "计划命中率" in adjusted["policy_note"]
    assert adjusted["policy_trade_plan_match_rate"] == 0.78
