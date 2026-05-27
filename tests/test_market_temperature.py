import pandas as pd

from quant_system.market.temperature import calculate_market_temperature, classify_temperature


def test_classify_temperature_maps_score_to_stance():
    assert classify_temperature(80)[0] == "hot"
    assert classify_temperature(20)[0] == "cold"


def test_calculate_market_temperature_uses_breadth_and_candidates():
    dates = pd.date_range("2024-01-01", periods=25)
    frame = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "symbol": ["000001"] * 25 + ["000002"] * 25,
            "open": list(range(10, 35)) + [10] * 25,
            "high": list(range(11, 36)) + [11] * 25,
            "low": list(range(9, 34)) + [9] * 25,
            "close": list(range(10, 35)) + [10] * 25,
            "volume": [1000] * 50,
        }
    )
    candidates = pd.DataFrame({"symbol": ["000001"]})

    temperature = calculate_market_temperature(frame, candidates)

    assert temperature.total_symbols == 2
    assert temperature.candidate_count == 1
    assert temperature.score > 0
