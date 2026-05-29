import pandas as pd

from quant_system.risk.pretrade import run_pretrade_check


def candidates():
    return pd.DataFrame(
        {
            "symbol": ["000001"],
            "name": ["Demo"],
            "score": [100],
            "risk_grade": ["medium"],
            "atr_stop_price": [33.8],
        }
    )


def test_pretrade_check_passes_disciplined_plan():
    result = run_pretrade_check(
        candidates(),
        {"regime": "warm", "stance": "适度进攻"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.10,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    assert result.status == "pass"
    assert result.allowed_pct == 0.12
    assert result.planned_value == 10000
    assert result.allowed_value == 12000
    assert result.max_loss_value == 789.47
    assert result.action_items


def test_pretrade_check_blocks_oversized_position():
    result = run_pretrade_check(
        candidates(),
        {"regime": "warm", "stance": "适度进攻"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.2,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    assert result.status == "block"
    assert any(check.name == "position_size" and check.status == "block" for check in result.checks)


def test_pretrade_check_warns_on_strategy_health_warning():
    result = run_pretrade_check(
        candidates(),
        {"regime": "warm", "stance": "适度进攻"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
        strategy_health={"strategy": "demo", "alert_level": "warn", "action": "keep", "alerts": ["execution_deviation"]},
    )

    assert result.status == "warn"
    assert result.allowed_pct == 0.06
    assert any(check.name == "strategy_health" and check.status == "warn" for check in result.checks)
    assert any("执行偏差过大" in check.message for check in result.checks)
    assert result.strategy_constraint["alert_level"] == "warn"
    assert result.to_dict()["strategy_constraint"]["note"]


def test_pretrade_check_blocks_on_strategy_health_pause():
    result = run_pretrade_check(
        candidates(),
        {"regime": "warm", "stance": "适度进攻"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
        strategy_health={"strategy": "demo", "alert_level": "block", "action": "pause", "alerts": ["mistake_cluster"]},
    )

    assert result.status == "block"
    assert result.allowed_pct == 0.0
    assert any(check.name == "strategy_health" and check.status == "block" for check in result.checks)
    assert any("错误集中" in check.message for check in result.checks)
    assert result.strategy_constraint["action"] == "pause"


def test_pretrade_check_warns_on_entry_price_deviation_and_high_risk():
    frame = candidates()
    frame["close"] = [35]
    frame["risk_grade"] = ["high"]
    result = run_pretrade_check(
        frame,
        {"regime": "warm", "stance": "适度进攻"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    assert result.status == "warn"
    assert result.candidate_snapshot["risk_grade"] == "high"
    assert any(check.name == "entry_price" and check.status == "warn" for check in result.checks)
    assert any(check.name == "risk_grade" and check.status == "warn" for check in result.checks)
