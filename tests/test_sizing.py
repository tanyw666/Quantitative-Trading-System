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
