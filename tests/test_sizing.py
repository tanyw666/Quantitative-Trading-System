import pandas as pd

from quant_system.risk.sizing import build_allocation_plan


def test_build_allocation_plan_reallocates_unfilled_capacity():
    candidates = pd.DataFrame(
        {
            "symbol": ["000001", "000002", "000003"],
            "name": ["A", "B", "C"],
            "score": [100, 90, 80],
            "risk_grade": ["high", "medium", "low"],
            "atr_stop_price": [9.0, 8.0, 7.0],
        }
    )

    plan = build_allocation_plan(
        candidates,
        {"regime": "warm", "stance": "test"},
        cash=100000,
        max_positions=3,
        regime_exposure={"warm": 0.6},
        cap_by_risk={"high": 0.06, "medium": 0.12, "low": 0.2, "unknown": 0.05},
    )

    assert len(plan.items) == 3
    assert plan.allocated_pct > 0.06
    assert plan.allocated_pct <= 0.6
    assert plan.items[1].target_pct > 0
    assert plan.items[2].target_pct > 0


def test_build_allocation_plan_halves_exposure_on_strategy_warn():
    candidates = pd.DataFrame(
        {
            "symbol": ["000001"],
            "name": ["A"],
            "score": [100],
            "risk_grade": ["low"],
            "atr_stop_price": [9.0],
        }
    )

    plan = build_allocation_plan(
        candidates,
        {"regime": "warm", "stance": "test"},
        cash=100000,
        max_positions=1,
        regime_exposure={"warm": 0.6},
        cap_by_risk={"low": 0.5, "unknown": 0.05},
        strategy_health={"strategy": "demo", "alert_level": "warn", "action": "keep", "alerts": ["execution_deviation"]},
    )

    assert plan.target_exposure_pct == 0.3
    assert plan.strategy_alert_level == "warn"
    assert "策略健康度预警" in plan.strategy_adjustment_note
    assert "执行偏差过大" in plan.strategy_adjustment_note
    assert "60.0%" in plan.strategy_adjustment_note
    assert "30.0%" in plan.strategy_adjustment_note
    assert plan.strategy_constraint == {
        "strategy": "demo",
        "alert_level": "warn",
        "action": "keep",
        "alerts": ["execution_deviation"],
        "note": plan.strategy_adjustment_note,
    }
    assert plan.to_dict()["strategy_constraint"]["note"] == plan.strategy_adjustment_note


def test_build_allocation_plan_blocks_exposure_on_strategy_pause():
    candidates = pd.DataFrame(
        {
            "symbol": ["000001"],
            "name": ["A"],
            "score": [100],
            "risk_grade": ["low"],
            "atr_stop_price": [9.0],
        }
    )

    plan = build_allocation_plan(
        candidates,
        {"regime": "warm", "stance": "test"},
        cash=100000,
        max_positions=1,
        regime_exposure={"warm": 0.6},
        cap_by_risk={"low": 0.5, "unknown": 0.05},
        strategy_health={"strategy": "demo", "alert_level": "block", "action": "pause", "alerts": ["mistake_cluster"]},
    )

    assert plan.target_exposure_pct == 0.0
    assert plan.allocated_pct == 0.0
    assert plan.strategy_action == "pause"
    assert "策略健康度阻断" in plan.strategy_adjustment_note
    assert "错误集中" in plan.strategy_adjustment_note
    assert plan.strategy_constraint["action"] == "pause"
    assert plan.strategy_constraint["alert_level"] == "block"
