from types import SimpleNamespace

import pandas as pd

import quant_system.cli as cli
from quant_system.storage.sqlite_store import SQLiteStore


class DemoStrategy:
    def screen(self, frame):
        return pd.DataFrame(
            {
                "symbol": ["000001"],
                "name": ["Demo"],
                "score": [90],
                "risk_grade": ["medium"],
                "close": [10.0],
            }
        )


def test_run_portfolio_confirm_writes_markdown(monkeypatch, tmp_path):
    output = tmp_path / "confirm.md"
    confirm_log = tmp_path / "execution_confirms.jsonl"
    battle_plan = tmp_path / "battle_plan.json"
    battle_plan.write_text(
        """
{
  "status": "pass",
  "decision": "ok",
  "buy_candidates": [
    {"symbol": "000001", "planned_pct": 0.1, "allowed_pct": 0.1, "entry_price": 10.0}
  ],
  "blocked_candidates": []
}
""".strip(),
        encoding="utf-8",
    )
    args = cli.build_parser().parse_args(
        [
            "portfolio",
            "confirm",
            "--csv",
            "prices.csv",
            "--symbol",
            "000001",
            "--current-price",
            "10",
            "--planned-pct",
            "0.1",
            "--stop-price",
            "9.5",
            "--target-price",
            "11.5",
            "--battle-plan",
            str(battle_plan),
            "--record",
            "--log",
            str(confirm_log),
            "--sqlite",
            str(tmp_path / "quant.sqlite"),
            "--format",
            "markdown",
            "--output",
            str(output),
        ]
    )
    monkeypatch.setattr(
        cli,
        "load_ohlcv_dataset",
        lambda *a, **k: pd.DataFrame({"symbol": ["000001"], "close": [10.0]}),
    )
    monkeypatch.setattr(cli, "strategy_from_args", lambda _args: DemoStrategy())
    monkeypatch.setattr(
        cli,
        "settings_from_args",
        lambda _args: SimpleNamespace(
            scoring=SimpleNamespace(weights={}),
            risk=SimpleNamespace(regime_exposure=None, cap_by_risk=None),
        ),
    )
    monkeypatch.setattr(cli, "enrich_and_score_candidates", lambda _frame, candidates, *_args, **_kwargs: candidates)
    monkeypatch.setattr(
        cli,
        "calculate_market_temperature",
        lambda *_args, **_kwargs: SimpleNamespace(to_dict=lambda: {"regime": "warm", "stance": "test"}),
    )
    monkeypatch.setattr(cli, "_current_strategy_health", lambda _args: {"strategy": "demo", "alert_level": "pass", "action": "keep"})
    monkeypatch.setattr(cli, "persist_constraint_audit", lambda *a, **k: None)

    cli.run_portfolio_confirm(args)

    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "Status: pass" in content
    assert "Suggested quantity: 1000 shares" in content
    assert confirm_log.exists()
    assert '"symbol": "000001"' in confirm_log.read_text(encoding="utf-8")
    records = SQLiteStore(tmp_path / "quant.sqlite").read_execution_confirmations(symbol="000001")
    assert records.loc[0, "status"] == "pass"


def test_battle_plan_from_args_raises_when_missing(tmp_path):
    args = SimpleNamespace(battle_plan=tmp_path / "missing.json")

    try:
        cli._battle_plan_from_args(args)
    except FileNotFoundError as exc:
        assert "Battle plan not found" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
