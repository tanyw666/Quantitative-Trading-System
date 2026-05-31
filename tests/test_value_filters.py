import pandas as pd

from quant_system.screening.scoring import score_candidates
from quant_system.screening.value_filters import add_value_filter_fields
from quant_system.risk.pretrade import run_pretrade_check


def test_value_filter_blocks_st_and_delisting_risk():
    frame = pd.DataFrame(
        {
            "symbol": ["000001", "000002"],
            "name": ["Normal", "*ST Demo"],
            "delisting_risk_flag": [False, True],
        }
    )

    result = add_value_filter_fields(frame)

    assert result.loc[0, "value_filter_status"] == "pass"
    assert result.loc[1, "value_filter_status"] == "block"
    assert bool(result.loc[1, "value_landmine_flag"]) is True


def test_scoring_carries_value_filter_warning_fields():
    frame = pd.DataFrame(
        {
            "symbol": ["000001"],
            "score": [80],
            "pe_ttm": [-5],
            "pb": [1.2],
            "market_cap": [10_000_000_000],
        }
    )

    scored = score_candidates(frame)

    assert scored.loc[0, "value_filter_status"] == "warn"
    assert "non-positive PE" in scored.loc[0, "value_filter_reason"]


def test_pretrade_blocks_value_landmine_candidate():
    frame = pd.DataFrame(
        {
            "symbol": ["000001"],
            "name": ["*ST Demo"],
            "score": [100],
            "risk_grade": ["medium"],
            "atr_stop_price": [8.8],
            "close": [10.0],
            "delisting_risk_flag": [True],
        }
    )

    result = run_pretrade_check(
        frame,
        {"regime": "warm", "stance": "watch"},
        symbol="000001",
        entry_price=10.0,
        planned_pct=0.05,
        cash=100000,
        stop_price=9.0,
        target_price=12.0,
    )

    assert result.status == "block"
    assert result.candidate_snapshot["value_filter_status"] == "block"
    assert any(check.name == "value_filter" and check.status == "block" for check in result.checks)
