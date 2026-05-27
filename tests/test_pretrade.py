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
