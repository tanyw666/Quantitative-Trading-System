import pandas as pd

import quant_system.cli as cli


def test_prefilter_dragon_universe_keeps_most_active_symbols():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2026-05-28",
                    "2026-05-28",
                    "2026-05-28",
                ]
            ),
            "symbol": ["000001", "000002", "000003"],
            "open": [10, 10, 10],
            "high": [11, 10.2, 10.1],
            "low": [9.8, 9.9, 9.95],
            "close": [10.8, 10.0, 10.0],
            "volume": [3000, 1000, 500],
            "momentum_20": [0.3, 0.05, 0.01],
            "volume_ratio_20": [4.0, 1.2, 0.8],
        }
    )

    filtered = cli.prefilter_dragon_universe(frame, "dragon_leader", 2)

    assert set(filtered["symbol"]) == {"000001", "000002"}


def test_prefilter_dragon_universe_skips_other_strategies():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-05-28", "2026-05-28"]),
            "symbol": ["000001", "000002"],
            "open": [10, 10],
            "high": [11, 10.2],
            "low": [9.8, 9.9],
            "close": [10.8, 10.0],
            "volume": [3000, 1000],
        }
    )

    filtered = cli.prefilter_dragon_universe(frame, "strong_stock_screen", 1)

    assert len(filtered) == len(frame)
