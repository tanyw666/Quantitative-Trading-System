import pandas as pd

from quant_system.optimizer.experiments import ExperimentCase, experiment_cases_from_mapping, preset_cases, run_parameter_experiments, walk_forward_selections


def sample_frame():
    dates = pd.date_range("2024-01-01", periods=30)
    return pd.DataFrame(
        {
            "date": list(dates) * 2,
            "symbol": ["000001"] * 30 + ["000002"] * 30,
            "open": list(range(10, 40)) + [10] * 30,
            "high": list(range(11, 41)) + [11] * 30,
            "low": list(range(9, 39)) + [9] * 30,
            "close": list(range(10, 40)) + [10] * 30,
            "volume": ([1000] * 24 + [3000] * 6) + [1000] * 30,
        }
    )


def test_preset_cases_returns_three_profiles():
    cases = preset_cases("strong_stock_basic")

    assert [case.name for case in cases] == ["conservative", "balanced", "aggressive"]


def test_preset_cases_returns_dragon_gap_grid():
    cases = preset_cases("dragon_next_open_gap")

    assert len(cases) == 12
    assert cases[0].strategy == "dragon_leader"


def test_walk_forward_selections_generates_historical_candidates():
    case = ExperimentCase(name="demo", params={"min_20d_return": 0.1, "min_volume_ratio": 1.2, "max_atr_pct": 0.2})

    selections = walk_forward_selections(sample_frame(), case, top=1, min_history=25)

    assert selections
    assert selections[0]["symbol"] == "000001"


def test_walk_forward_selections_supports_dragon_strategy_metadata():
    case = ExperimentCase(
        name="dragon",
        strategy="dragon_leader",
        params={"entry_gate": "pass", "entry_model": "next_open", "max_next_open_gap": 0.07, "min_next_open_gap": -0.03},
    )

    selections = walk_forward_selections(dragon_frame(), case, top=1, min_history=25)

    assert selections
    assert selections[0]["symbol"] == "000001"
    assert selections[0]["entry_gate"] == "pass"


def test_run_parameter_experiments_returns_summary():
    case = ExperimentCase(name="demo", params={"min_20d_return": 0.1, "min_volume_ratio": 1.2, "max_atr_pct": 0.2})

    results = run_parameter_experiments(sample_frame(), [case], horizons=(1,), top=1, min_history=25)

    assert results[0].name == "demo"
    assert results[0].selection_count > 0


def test_experiment_cases_from_mapping_accepts_cases_key():
    cases = experiment_cases_from_mapping({"cases": [{"name": "demo", "params": {"min_20d_return": 0.1}}]})

    assert cases[0].name == "demo"


def dragon_frame():
    dates = pd.date_range("2024-01-01", periods=27)
    closes = [10.0] * 23 + [11.0, 12.1, 12.4, 13.0]
    opens = [10.0] * 23 + [10.8, 11.8, 12.3, 12.5]
    highs = [10.2] * 23 + [11.0, 12.1, 12.8, 13.2]
    lows = [9.8] * 23 + [10.8, 11.8, 12.0, 12.4]
    volumes = [1000] * 23 + [4000, 4000, 3000, 3200]
    return pd.DataFrame(
        {
            "date": dates,
            "symbol": ["000001"] * 27,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )
