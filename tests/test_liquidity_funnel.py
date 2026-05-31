import pandas as pd

from quant_system.screening.liquidity_funnel import (
    LiquidityFunnelConfig,
    apply_liquidity_funnel,
    limit_recent_trading_days,
)


def test_limit_recent_trading_days_keeps_last_unique_bars():
    frame = pd.DataFrame(
        {
            "date": [
                "2026-05-26",
                "2026-05-27",
                "2026-05-28",
                "2026-05-29",
                "2026-05-26",
                "2026-05-27",
                "2026-05-28",
                "2026-05-29",
            ],
            "symbol": ["000001"] * 4 + ["000002"] * 4,
            "close": [1] * 8,
        }
    )

    result = limit_recent_trading_days(frame, 2)

    assert sorted(result["date"].astype(str).unique().tolist()) == ["2026-05-28", "2026-05-29"]


def test_apply_liquidity_funnel_tags_core_and_expansion_candidates():
    candidates = pd.DataFrame(
        [
            {"symbol": "000001", "name": "A", "score": 80.0, "close": 10.0},
            {"symbol": "000002", "name": "B", "score": 70.0, "close": 9.0},
            {"symbol": "000003", "name": "C", "score": 60.0, "close": 8.0},
        ]
    )
    frame = pd.DataFrame(
        {
            "date": ["2026-05-29"] * 3,
            "symbol": ["000001", "000002", "000003"],
            "close": [10.0, 9.0, 8.0],
            "volume": [1000, 900, 800],
            "amount": [300_000_000, 180_000_000, 50_000_000],
        }
    )

    result = apply_liquidity_funnel(
        candidates,
        frame,
        LiquidityFunnelConfig(
            enabled=True,
            mode="tag",
            conservative_top_n=1,
            default_top_n=2,
            aggressive_top_n=3,
            min_traded_value=200_000_000,
        ),
    )

    assert result["symbol"].tolist() == ["000001", "000002", "000003"]
    assert result.loc[0, "funnel_stage"] == "core_conservative"
    assert bool(result.loc[0, "liquidity_pass"]) is True
    assert result.loc[1, "funnel_stage"] == "core_standard"
    assert bool(result.loc[1, "liquidity_pass"]) is True
    assert result.loc[2, "funnel_stage"] == "core_aggressive"
    assert bool(result.loc[2, "liquidity_pass"]) is False


def test_apply_liquidity_funnel_intersect_mode_filters_expansion():
    candidates = pd.DataFrame(
        [
            {"symbol": "000001", "name": "A", "score": 80.0, "close": 10.0},
            {"symbol": "000002", "name": "B", "score": 70.0, "close": 9.0},
        ]
    )
    frame = pd.DataFrame(
        {
            "date": ["2026-05-29", "2026-05-29"],
            "symbol": ["000001", "000002"],
            "close": [10.0, 9.0],
            "volume": [1000, 900],
            "amount": [300_000_000, 50_000_000],
        }
    )

    result = apply_liquidity_funnel(
        candidates,
        frame,
        LiquidityFunnelConfig(
            enabled=True,
            mode="intersect",
            conservative_top_n=1,
            default_top_n=1,
            aggressive_top_n=2,
            min_traded_value=200_000_000,
        ),
    )

    assert result["symbol"].tolist() == ["000001"]


def test_apply_liquidity_funnel_aggressive_profile_keeps_wider_pool():
    candidates = pd.DataFrame(
        [
            {"symbol": "000001", "name": "A", "score": 80.0, "close": 10.0},
            {"symbol": "000002", "name": "B", "score": 70.0, "close": 9.0},
            {"symbol": "000003", "name": "C", "score": 60.0, "close": 8.0},
        ]
    )
    frame = pd.DataFrame(
        {
            "date": ["2026-05-29"] * 3,
            "symbol": ["000001", "000002", "000003"],
            "close": [10.0, 9.0, 8.0],
            "volume": [1000, 900, 800],
            "amount": [300_000_000, 180_000_000, 50_000_000],
        }
    )

    result = apply_liquidity_funnel(
        candidates,
        frame,
        LiquidityFunnelConfig(
            enabled=True,
            mode="intersect",
            profile="aggressive",
            conservative_top_n=1,
            default_top_n=2,
            aggressive_top_n=3,
            min_traded_value=999_000_000,
        ),
    )

    assert result["symbol"].tolist() == ["000001", "000002", "000003"]
    assert result.loc[2, "funnel_stage"] == "core_aggressive"
