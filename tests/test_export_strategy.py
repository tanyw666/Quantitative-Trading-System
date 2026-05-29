import pytest

from quant_system.optimizer.export_strategy import strategy_config_from_summary


def sample_summary():
    return {
        "preferred_horizon": 1,
        "min_count": 5,
        "recommendation": {
            "name": "gap_hi_0.03_lo_-0.01",
            "strategy": "dragon_leader",
            "params": {"entry_gate": "pass", "entry_model": "next_open", "max_next_open_gap": 0.03},
            "scoring_weights": {"dragon_score": 0.7},
            "score": 0.05,
        },
    }


def test_strategy_config_from_summary_exports_recommended_params():
    config = strategy_config_from_summary(sample_summary())

    assert config["strategy"] == "dragon_leader"
    assert config["description"] == "由实验摘要自动导出的推荐策略。观察周期=1日，最小样本=5，参数组=gap_hi_0.03_lo_-0.01"
    assert config["params"]["max_next_open_gap"] == 0.03
    assert config["scoring_weights"] == {"dragon_score": 0.7}
    assert config["constraint_policy"]["window_days"] == 5.0
    assert config["source"]["recommended_case"] == "gap_hi_0.03_lo_-0.01"


def test_strategy_config_from_summary_uses_recommended_constraint_policy():
    summary = sample_summary()
    summary["recommendation"]["constraint_policy"] = {"window_days": 3, "warn_exposure_multiplier": 0.3}

    config = strategy_config_from_summary(summary)

    assert config["constraint_policy"] == {"window_days": 3, "warn_exposure_multiplier": 0.3}


def test_strategy_config_from_summary_requires_recommendation():
    with pytest.raises(ValueError):
        strategy_config_from_summary({"recommendation": None})
