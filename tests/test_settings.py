from quant_system.config.settings import SystemSettings


def test_system_settings_defaults_are_reasonable():
    settings = SystemSettings()
    assert settings.scoring.weights["momentum_20"] == 0.5
    assert settings.risk.cap_by_risk["medium"] == 0.12


def test_system_settings_from_mapping_overrides_defaults():
    settings = SystemSettings.from_mapping(
        {
            "scoring": {"weights": {"momentum_20": 0.7}},
            "risk": {
                "regime_exposure": {"warm": 0.5},
                "cap_by_risk": {"medium": 0.1},
            },
        }
    )

    assert settings.scoring.weights["momentum_20"] == 0.7
    assert settings.risk.regime_exposure["warm"] == 0.5
    assert settings.risk.cap_by_risk["medium"] == 0.1
