import pandas as pd

from quant_system.market.sectors import (
    annotate_candidates_with_sector_strength,
    calculate_sector_strength,
    detect_sector_column,
    filter_candidates_by_top_sectors,
)


def test_detect_sector_column_prefers_sector_then_industry():
    assert detect_sector_column(pd.DataFrame({"industry": ["Bank"]})) == "industry"
    assert detect_sector_column(pd.DataFrame({"sector": ["Finance"], "industry": ["Bank"]})) == "sector"


def test_calculate_sector_strength_ranks_strong_sector():
    dates = pd.date_range("2024-01-01", periods=25)
    frame = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "symbol": ["000001"] * 25 + ["000002"] * 25,
            "industry": ["Bank"] * 25 + ["Property"] * 25,
            "open": list(range(10, 35)) + [10] * 25,
            "high": list(range(11, 36)) + [11] * 25,
            "low": list(range(9, 34)) + [9] * 25,
            "close": list(range(10, 35)) + [10] * 25,
            "volume": [1000] * 50,
        }
    )
    candidates = pd.DataFrame({"symbol": ["000001"]})

    sectors = calculate_sector_strength(frame, candidates, top=2)

    assert sectors.loc[0, "sector"] == "Bank"
    assert sectors.loc[0, "candidate_count"] == 1


def test_annotate_and_filter_candidates_by_top_sectors():
    candidates = pd.DataFrame(
        {
            "symbol": ["000001", "000002"],
            "industry": ["Bank", "Property"],
            "score": [50, 90],
        }
    )
    sectors = pd.DataFrame(
        {
            "sector": ["Bank", "Property"],
            "strength_score": [80, 20],
        }
    )

    annotated = annotate_candidates_with_sector_strength(candidates, sectors)
    filtered = filter_candidates_by_top_sectors(annotated, sectors, top_n=1)

    assert annotated.loc[0, "sector_strength_score"] == 80
    assert annotated.loc[0, "sector_rank"] == 1
    assert filtered["symbol"].tolist() == ["000001"]
