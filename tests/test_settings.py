from quant_system.config.settings import SystemSettings
import pytest


def test_system_settings_defaults_are_reasonable():
    settings = SystemSettings()
    assert settings.scoring.weights["momentum_20"] == 0.5
    assert settings.risk.cap_by_risk["medium"] == 0.12
    assert settings.risk.constraint_policy.window_days == 5
    assert settings.risk.constraint_policy.warn_exposure_multiplier == 0.5


def test_system_settings_from_mapping_overrides_defaults():
    settings = SystemSettings.from_mapping(
        {
            "scoring": {"weights": {"momentum_20": 0.7}},
            "risk": {
                "regime_exposure": {"warm": 0.5},
                "cap_by_risk": {"medium": 0.1},
                "constraint_policy": {"recover_after_clean_days": 4, "warn_exposure_multiplier": 0.4},
            },
        }
    )

    assert settings.scoring.weights["momentum_20"] == 0.7
    assert settings.risk.regime_exposure["warm"] == 0.5
    assert settings.risk.cap_by_risk["medium"] == 0.1
    assert settings.risk.constraint_policy.recover_after_clean_days == 4
    assert settings.risk.constraint_policy.warn_exposure_multiplier == 0.4


def test_system_settings_rejects_non_mapping_sections():
    with pytest.raises(ValueError, match="scoring must be a mapping"):
        SystemSettings.from_mapping({"scoring": []})


def test_system_settings_loads_data_source_preferences():
    settings = SystemSettings.from_mapping({"data_sources": {"daily_source": "tencent", "universe_source": "akshare"}})
    assert settings.data_sources.daily_source == "tencent"
    assert settings.data_sources.universe_source == "akshare"


def test_constraint_policy_supports_strategy_overrides():
    settings = SystemSettings.from_mapping(
        {
            "risk": {
                "constraint_policy": {
                    "recover_after_clean_days": 3,
                    "strategies": {
                        "dragon-leader": {"recover_after_clean_days": 5, "warn_exposure_multiplier": 0.3}
                    },
                }
            }
        }
    )

    dragon = settings.risk.constraint_policy.kwargs_for("dragon_leader")
    base = settings.risk.constraint_policy.kwargs_for("strong_stock_screen")

    assert dragon["recover_after_clean_days"] == 5
    assert dragon["warn_exposure_multiplier"] == 0.3
    assert base["recover_after_clean_days"] == 3
