from pathlib import Path

import pandas as pd

from quant_system.strategies.configurable import ConfigurableScreenStrategy


def test_configurable_strategy_supports_book_rule_fields(tmp_path: Path):
    config_path = tmp_path / "configurable.yaml"
    config_path.write_text(
        """
name: configurable_book_rules
condition:
  all:
    - field: entry_structure_score
      op: gte
      value: 55
    - field: chase_risk_score
      op: lte
      value: 35
    - field: false_breakout_flag
      op: eq
      value: false
    - field: value_filter_status
      op: neq
      value: block
""".strip(),
        encoding="utf-8",
    )
    strategy = ConfigurableScreenStrategy.from_yaml(config_path)
    dates = pd.date_range("2024-01-01", periods=25)
    frame = pd.DataFrame(
        {
            "date": dates,
            "symbol": ["AAA"] * 25,
            "name": ["Demo"] * 25,
            "open": [19.6] * 20 + [23.6, 24.6, 25.6, 26.6, 27.1],
            "high": [20.1] * 20 + [24.1, 25.1, 26.1, 27.1, 27.6],
            "low": [19.4] * 20 + [23.4, 24.4, 25.4, 26.4, 26.9],
            "close": [20] * 20 + [24, 25, 26, 27, 27.5],
            "volume": [1000] * 24 + [2200],
        }
    )

    selected = strategy.screen(frame)

    assert selected["symbol"].tolist() == ["AAA"]
    assert selected["entry_structure_score"].iloc[0] >= 55
    assert selected["chase_risk_score"].iloc[0] <= 35
    assert selected["value_filter_status"].iloc[0] == "pass"
