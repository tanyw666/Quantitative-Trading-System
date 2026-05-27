import pandas as pd

from quant_system.risk.sizing import build_allocation_plan


def test_build_allocation_plan_caps_single_position_by_risk():
    candidates = pd.DataFrame(
        {
            "symbol": ["000001"],
            "name": ["Demo"],
            "score": [100],
            "risk_grade": ["high"],
            "atr_stop_price": [9.5],
        }
    )
    temperature = {"regime": "hot", "stance": "进攻"}

    plan = build_allocation_plan(candidates, temperature, cash=100000, max_positions=5)

    assert plan.target_exposure_pct == 0.8
    assert plan.items[0].target_pct == 0.06
    assert plan.items[0].target_value == 6000


def test_build_allocation_plan_returns_empty_when_market_frozen():
    candidates = pd.DataFrame({"symbol": ["000001"], "score": [100], "risk_grade": ["low"]})

    plan = build_allocation_plan(candidates, {"regime": "frozen", "stance": "空仓"}, cash=100000)

    assert plan.allocated_pct == 0.0
    assert plan.items == []
