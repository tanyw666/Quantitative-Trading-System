import pandas as pd

from quant_system.screening.scoring import score_candidates


def test_score_candidates_ranks_high_momentum_volume_and_low_volatility():
    frame = pd.DataFrame(
        {
            "symbol": ["000001", "000002"],
            "close": [10, 10],
            "momentum_20": [0.2, 0.1],
            "volume_ratio_20": [2.0, 1.0],
            "atr_14": [0.3, 1.0],
            "atr_pct_14": [0.03, 0.1],
        }
    )

    scored = score_candidates(frame)

    assert scored.loc[0, "symbol"] == "000001"
    assert scored.loc[0, "score"] > scored.loc[1, "score"]
    assert scored.loc[0, "risk_grade"] == "low"
    assert scored.loc[0, "atr_stop_price"] == 9.4


def test_score_candidates_can_use_sector_strength_weight():
    frame = pd.DataFrame(
        {
            "symbol": ["000001", "000002"],
            "close": [10, 10],
            "momentum_20": [0.1, 0.2],
            "volume_ratio_20": [1.0, 2.0],
            "atr_pct_14": [0.03, 0.03],
            "sector_strength_score": [90, 10],
        }
    )

    scored = score_candidates(
        frame,
        weights={"momentum_20": 0, "volume_ratio_20": 0, "atr_pct_14": 0, "sector_strength_score": 1},
    )

    assert scored.loc[0, "symbol"] == "000001"
    assert scored.loc[0, "score"] > scored.loc[1, "score"]


def test_score_candidates_handles_frames_without_scoring_columns():
    frame = pd.DataFrame(
        {
            "symbol": ["000001"],
            "close": [10],
        }
    )

    scored = score_candidates(frame, weights={})

    assert scored.loc[0, "score"] == 0.0
    assert scored.loc[0, "risk_grade"] == "unknown"
