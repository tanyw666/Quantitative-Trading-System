import pandas as pd

from quant_system.strategies.dragon_leader import (
    DragonLeaderStrategy,
    add_dragon_factors,
    infer_limit_pct,
    latest_dragon_diagnostics,
)
from quant_system.strategies.registry import create_strategy


def test_infer_limit_pct_by_board_and_symbol():
    assert infer_limit_pct(pd.Series({"symbol": "000001"})) == 0.10
    assert infer_limit_pct(pd.Series({"symbol": "300001"})) == 0.20
    assert infer_limit_pct(pd.Series({"symbol": "688001"})) == 0.20
    assert infer_limit_pct(pd.Series({"symbol": "830000"})) == 0.30
    assert infer_limit_pct(pd.Series({"symbol": "000001", "board": "CHINEXT"})) == 0.20


def test_add_dragon_factors_counts_consecutive_limit_up():
    frame = _limit_up_frame()

    factors = add_dragon_factors(frame)
    latest = factors[factors["symbol"] == "000001"].tail(1).iloc[0]

    assert latest["is_limit_up"]
    assert latest["consecutive_limit_up"] == 2
    assert latest["seal_quality_score"] > 80
    assert latest["reseal_candidate"]
    assert latest["dragon_state"] == "sealed"
    assert latest["entry_gate"] == "pass"


def test_dragon_leader_strategy_selects_latest_two_board_candidate():
    strategy = DragonLeaderStrategy(min_consecutive_limit_up=2, min_volume_ratio=1.5)

    selected = strategy.screen(_limit_up_frame())

    assert selected["symbol"].tolist() == ["000001"]
    assert selected.loc[0, "consecutive_limit_up"] == 2
    assert selected.loc[0, "dragon_score"] > 0
    assert selected.loc[0, "seal_quality_score"] > 80
    assert "reseal-candidate" in selected.loc[0, "dragon_tags"]
    assert selected.loc[0, "entry_gate"] == "pass"


def test_dragon_leader_strategy_selects_weak_to_strong_candidate():
    strategy = DragonLeaderStrategy(min_consecutive_limit_up=2, min_volume_ratio=1.5)

    selected = strategy.screen(_weak_to_strong_frame())

    assert selected["symbol"].tolist() == ["000003"]
    assert selected.loc[0, "weak_to_strong"]


def test_registry_creates_dragon_leader_strategy():
    assert create_strategy("dragon_leader").name == "dragon_leader"


def test_dragon_factors_detect_failed_limit_up_pressure():
    factors = add_dragon_factors(_failed_then_limit_frame())
    latest = factors.tail(1).iloc[0]

    assert latest["is_limit_up"]
    assert latest["recent_failed_limit_up_3"] == 1
    assert latest["failed_limit_repair"]
    assert latest["seal_quality_score"] < 100
    assert latest["entry_gate"] == "watch"


def test_latest_dragon_diagnostics_returns_latest_symbol_snapshot():
    diagnostics = latest_dragon_diagnostics(_limit_up_frame(), "000001")

    assert diagnostics["symbol"] == "000001"
    assert diagnostics["consecutive_limit_up"] == 2
    assert diagnostics["dragon_score"] > 0
    assert "dragon_tags" in diagnostics
    assert diagnostics["entry_gate"] == "pass"


def test_dragon_entry_gate_blocks_one_price_limit_up():
    factors = add_dragon_factors(_one_price_limit_frame())
    latest = factors.tail(1).iloc[0]

    assert latest["one_price_limit_up"]
    assert latest["entry_gate"] == "block"
    assert "one-price" in latest["entry_reasons"]


def test_entry_gate_policy_filters_buy_signals():
    all_strategy = DragonLeaderStrategy(min_consecutive_limit_up=2, min_volume_ratio=1.5, entry_gate="all")
    pass_strategy = DragonLeaderStrategy(min_consecutive_limit_up=2, min_volume_ratio=1.5, entry_gate="pass")

    all_signals = all_strategy.generate_signals(_one_price_limit_frame())
    pass_signals = pass_strategy.generate_signals(_one_price_limit_frame())

    assert all_signals.tail(1)["buy_signal"].iloc[0]
    assert not pass_signals.tail(1)["buy_signal"].iloc[0]


def test_entry_gate_policy_can_allow_watch_signals():
    pass_watch_strategy = DragonLeaderStrategy(min_consecutive_limit_up=2, min_volume_ratio=1.5, entry_gate="pass-watch")
    pass_strategy = DragonLeaderStrategy(min_consecutive_limit_up=2, min_volume_ratio=1.5, entry_gate="pass")

    watch_signals = pass_watch_strategy.generate_signals(_failed_then_limit_frame())
    pass_signals = pass_strategy.generate_signals(_failed_then_limit_frame())

    assert watch_signals.tail(1)["entry_gate"].iloc[0] == "watch"
    assert watch_signals.tail(1)["buy_signal"].iloc[0]
    assert not pass_signals.tail(1)["buy_signal"].iloc[0]


def test_next_open_entry_model_delays_buy_signal():
    strategy = DragonLeaderStrategy(
        min_consecutive_limit_up=2,
        min_volume_ratio=1.5,
        entry_gate="pass",
        entry_model="next_open",
    )

    signals = strategy.generate_signals(_limit_up_with_next_day_frame())

    assert signals.iloc[-2]["dragon_setup_signal"]
    assert not signals.iloc[-2]["buy_signal"]
    assert signals.iloc[-1]["buy_signal"]
    assert signals.iloc[-1]["next_open_entry_ok"]


def test_next_open_screen_keeps_setup_context():
    strategy = DragonLeaderStrategy(
        min_consecutive_limit_up=2,
        min_volume_ratio=1.5,
        entry_gate="pass",
        entry_model="next_open",
    )

    selected = strategy.screen(_limit_up_with_next_day_frame())

    assert selected.loc[0, "date"] == pd.Timestamp("2024-01-26")
    assert selected.loc[0, "setup_date"] == pd.Timestamp("2024-01-25")
    assert selected.loc[0, "entry_gate"] == "pass"
    assert selected.loc[0, "dragon_state"] == "sealed"


def test_next_open_entry_model_blocks_overheated_open():
    strategy = DragonLeaderStrategy(
        min_consecutive_limit_up=2,
        min_volume_ratio=1.5,
        entry_gate="pass",
        entry_model="next_open",
        max_next_open_gap=0.07,
    )

    signals = strategy.generate_signals(_limit_up_with_next_day_frame(next_open=13.1))

    assert not signals.iloc[-1]["buy_signal"]
    assert "gap-too-high" in signals.iloc[-1]["next_open_entry_reasons"]


def test_next_open_entry_model_blocks_weak_open():
    strategy = DragonLeaderStrategy(
        min_consecutive_limit_up=2,
        min_volume_ratio=1.5,
        entry_gate="pass",
        entry_model="next_open",
        min_next_open_gap=-0.03,
    )

    signals = strategy.generate_signals(_limit_up_with_next_day_frame(next_open=11.6))

    assert not signals.iloc[-1]["buy_signal"]
    assert "gap-too-low" in signals.iloc[-1]["next_open_entry_reasons"]


def _limit_up_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=25)
    closes = [10.0] * 23 + [11.0, 12.1]
    opens = [10.0] * 23 + [10.8, 11.8]
    highs = closes
    lows = [9.8] * 23 + [10.8, 11.8]
    volumes = [1000] * 23 + [4000, 4000]
    flat = [10.0] * 25
    return pd.DataFrame(
        {
            "date": list(dates) * 2,
            "symbol": ["000001"] * 25 + ["000002"] * 25,
            "name": ["Dragon"] * 25 + ["Flat"] * 25,
            "open": opens + flat,
            "high": highs + flat,
            "low": lows + flat,
            "close": closes + flat,
            "volume": volumes + [1000] * 25,
        }
    )


def _weak_to_strong_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=25)
    closes = [10.0] * 23 + [10.0, 11.0]
    opens = [10.0] * 23 + [10.5, 10.1]
    highs = [10.2] * 23 + [10.6, 11.0]
    lows = [9.8] * 23 + [9.9, 10.1]
    volumes = [1000] * 24 + [4000]
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": ["000003"] * 25,
            "name": ["WeakStrong"] * 25,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def _failed_then_limit_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=25)
    closes = [10.0] * 23 + [10.0, 11.0]
    opens = [10.0] * 23 + [10.2, 10.5]
    highs = [10.2] * 23 + [11.0, 11.0]
    lows = [9.8] * 23 + [9.9, 10.5]
    volumes = [1000] * 24 + [4000]
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": ["000004"] * 25,
            "name": ["FailedThenLimit"] * 25,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def _one_price_limit_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=25)
    closes = [10.0] * 24 + [11.0]
    opens = [10.0] * 24 + [11.0]
    highs = [10.2] * 24 + [11.0]
    lows = [9.8] * 24 + [11.0]
    volumes = [1000] * 24 + [4000]
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": ["000005"] * 25,
            "name": ["OnePrice"] * 25,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def _limit_up_with_next_day_frame(next_open: float = 12.3) -> pd.DataFrame:
    frame = _limit_up_frame()
    extra = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-26")],
            "symbol": ["000001"],
            "name": ["Dragon"],
            "open": [next_open],
            "high": [max(next_open, 12.8)],
            "low": [min(next_open, 12.0)],
            "close": [12.4],
            "volume": [3000],
        }
    )
    return pd.concat([frame[frame["symbol"] == "000001"], extra], ignore_index=True)
