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
            "close": [37.5],
            "entry_structure_score": [68.0],
            "chase_risk_score": [20.0],
            "candle_warning_count": [0],
            "volume_price_state": ["confirmed"],
            "false_breakout_flag": [False],
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


def test_pretrade_check_blocks_on_review_memory_pressure():
    result = run_pretrade_check(
        candidates(),
        {"regime": "warm", "stance": "适度进攻"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
        strategy_health={
            "strategy": "demo",
            "alert_level": "pass",
            "action": "keep",
            "alerts": [],
            "lifecycle_pressure": {
                "alert_level": "block",
                "action": "pause",
                "summary": "window 5; lifecycle block 2, warn 1; trend worsening",
            },
        },
    )

    assert result.status == "block"
    assert any(check.name == "review_memory" and check.status == "block" for check in result.checks)
    assert any("Review memory blocks new risk" in check.message for check in result.checks)


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


def test_pretrade_check_blocks_low_liquidity_candidate():
    frame = candidates()
    frame["traded_value"] = [5_000_000]
    result = run_pretrade_check(
        frame,
        {"regime": "warm", "stance": "閫傚害杩涙敾"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    assert result.status == "block"
    assert any(check.name == "candidate_liquidity" and check.status == "block" for check in result.checks)


def test_pretrade_check_blocks_negative_ma20_slope():
    frame = candidates()
    frame["ma20_slope_5"] = [-0.02]
    frame["close_to_ma20"] = [0.02]
    result = run_pretrade_check(
        frame,
        {"regime": "warm", "stance": "閫傚害杩涙敾"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    assert result.status == "block"
    assert any(check.name == "candidate_trend_quality" and check.status == "block" for check in result.checks)


def test_pretrade_check_blocks_false_breakout_candidate():
    frame = candidates()
    frame["false_breakout_flag"] = [True]
    result = run_pretrade_check(
        frame,
        {"regime": "warm", "stance": "闁倸瀹虫潻娑欐暰"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    assert result.status == "block"
    assert any(check.name == "false_breakout" and check.status == "block" for check in result.checks)


def test_pretrade_check_blocks_exhaustion_volume_price_state():
    frame = candidates()
    frame["volume_price_state"] = ["exhaustion_warning"]
    result = run_pretrade_check(
        frame,
        {"regime": "warm", "stance": "闁倸瀹虫潻娑欐暰"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    assert result.status == "block"
    assert any(check.name == "volume_price_confirmation" and check.status == "block" for check in result.checks)


def test_pretrade_check_warns_on_marginal_structure_and_chase_risk():
    frame = candidates()
    frame["entry_structure_score"] = [52.0]
    frame["chase_risk_score"] = [50.0]
    frame["volume_price_state"] = ["quiet_pullback"]
    frame["close"] = [37.0]
    result = run_pretrade_check(
        frame,
        {"regime": "warm", "stance": "闁倸瀹虫潻娑欐暰"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    assert result.status == "warn"
    assert any(check.name == "entry_structure" and check.status == "warn" for check in result.checks)
    assert any(check.name == "chase_risk" and check.status == "warn" for check in result.checks)
    assert any(check.name == "volume_price_confirmation" and check.status == "warn" for check in result.checks)


def test_pretrade_check_blocks_on_multiple_candle_warnings():
    frame = candidates()
    frame["candle_warning_count"] = [2]
    result = run_pretrade_check(
        frame,
        {"regime": "warm", "stance": "闁倸瀹虫潻娑欐暰"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    assert result.status == "block"
    assert any(check.name == "candle_warning" and check.status == "block" for check in result.checks)


def test_pretrade_check_blocks_tape_distribution_warning():
    frame = candidates()
    frame["tape_distribution_warning"] = [True]
    frame["tape_pressure_score"] = [-30.0]
    result = run_pretrade_check(
        frame,
        {"regime": "warm", "stance": "闁倸瀹虫潻娑欐暰"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.05,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    assert result.status == "block"
    assert any(check.name == "tape_reading" and check.status == "block" for check in result.checks)
