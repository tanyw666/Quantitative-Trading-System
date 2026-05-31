import json
from argparse import Namespace
from types import SimpleNamespace

import pandas as pd

import quant_system.cli as cli
from quant_system.reports.final_battle_plan import build_final_battle_plan
from quant_system.risk.pretrade import run_pretrade_check
from quant_system.risk.sizing import build_allocation_plan


def test_attribution_block_constraint_reaches_screen_sizing_pretrade_and_battle_plan(tmp_path):
    constraint_log = tmp_path / "constraints.jsonl"
    _write_constraint(
        constraint_log,
        alert_level="block",
        action="pause",
        exposure_multiplier=0.0,
        alerts=["attribution_execution", "missing_execution_confirmation"],
    )
    args = _strategy_args(tmp_path, constraint_log)
    health = cli._current_strategy_health(args)

    assert health["alert_level"] == "block"
    assert health["action"] == "pause"
    assert health["policy_exposure_multiplier"] == 0.0
    assert "attribution_execution" in health["alerts"]

    candidates = cli.apply_strategy_gate_to_candidates(_candidate_frame(), health)
    assert bool(candidates.loc[0, "strategy_actionable"]) is False
    assert candidates.loc[0, "strategy_exposure_multiplier"] == 0.0

    allocation = build_allocation_plan(
        candidates,
        {"regime": "warm", "stance": "test"},
        cash=100000,
        max_positions=1,
        strategy_health=health,
    )
    assert allocation.target_exposure_pct == 0.0
    assert allocation.items == []
    assert allocation.strategy_constraint["alert_level"] == "block"

    pretrade = run_pretrade_check(
        candidates,
        {"regime": "warm", "stance": "test"},
        symbol="000001",
        entry_price=10.0,
        planned_pct=0.05,
        cash=100000,
        stop_price=9.0,
        target_price=12.0,
        strategy_health=health,
    )
    assert pretrade.status == "block"
    assert pretrade.allowed_pct == 0.0
    assert any(check.name == "strategy_health" and check.status == "block" for check in pretrade.checks)

    battle_plan = build_final_battle_plan(
        {
            "market_temperature": {"regime": "warm", "stance": "test"},
            "allocation_plan": allocation.to_dict(),
            "holding_risk": {"status": "pass"},
            "holding_action_plan": {"status": "pass"},
            "exit_plan": {"status": "pass"},
            "strategy_health": [health],
            "pretrade_checks": [pretrade.to_dict()],
        }
    )
    assert battle_plan["status"] == "block"
    assert "strategy gate blocks new positions" in battle_plan["reasons"]


def test_attribution_warn_constraint_marks_candidates_and_reduces_sizing(tmp_path):
    constraint_log = tmp_path / "constraints.jsonl"
    _write_constraint(
        constraint_log,
        alert_level="warn",
        action="reduce",
        exposure_multiplier=0.5,
        alerts=["attribution_planning"],
    )
    args = _strategy_args(tmp_path, constraint_log)
    health = cli._current_strategy_health(args)

    assert health["alert_level"] == "warn"
    assert health["action"] == "reduce"

    candidates = cli.apply_strategy_gate_to_candidates(_candidate_frame(), health)
    assert bool(candidates.loc[0, "strategy_actionable"]) is True
    assert candidates.loc[0, "strategy_exposure_multiplier"] == 0.5

    allocation = build_allocation_plan(
        candidates,
        {"regime": "warm", "stance": "test"},
        cash=100000,
        max_positions=1,
        regime_exposure={"warm": 0.6},
        cap_by_risk={"medium": 0.5, "unknown": 0.05},
        strategy_health=health,
    )
    assert allocation.target_exposure_pct == 0.3
    assert allocation.strategy_constraint["alert_level"] == "warn"

    pretrade = run_pretrade_check(
        candidates,
        {"regime": "warm", "stance": "test"},
        symbol="000001",
        entry_price=10.0,
        planned_pct=0.05,
        cash=100000,
        stop_price=9.0,
        target_price=12.0,
        max_positions=1,
        regime_exposure={"warm": 0.6},
        cap_by_risk={"medium": 0.5, "unknown": 0.05},
        strategy_health=health,
    )
    assert pretrade.status == "warn"
    assert any(check.name == "strategy_health" and check.status == "warn" for check in pretrade.checks)


def test_screen_parsers_accept_constraint_inputs():
    screen_args = cli.build_parser().parse_args(
        [
            "screen",
            "--csv",
            "prices.csv",
            "--constraint-log",
            "constraints.jsonl",
            "--disable-approval-cooldown",
        ]
    )
    dragon_args = cli.build_parser().parse_args(
        [
            "dragon",
            "screen",
            "--csv",
            "prices.csv",
            "--constraint-log",
            "constraints.jsonl",
            "--disable-approval-cooldown",
        ]
    )

    assert str(screen_args.constraint_log) == "constraints.jsonl"
    assert screen_args.disable_approval_cooldown is True
    assert str(dragon_args.constraint_log) == "constraints.jsonl"
    assert dragon_args.disable_approval_cooldown is True


def test_run_screen_does_not_record_blocked_candidates(monkeypatch, tmp_path, capsys):
    constraint_log = tmp_path / "constraints.jsonl"
    tracker = tmp_path / "selections.jsonl"
    _write_constraint(
        constraint_log,
        alert_level="block",
        action="pause",
        exposure_multiplier=0.0,
        alerts=["attribution_execution"],
    )
    args = cli.build_parser().parse_args(
        [
            "screen",
            "--csv",
            "prices.csv",
            "--constraint-log",
            str(constraint_log),
            "--tracker",
            str(tracker),
            "--record",
            "--disable-approval-cooldown",
        ]
    )

    class DummyStrategy:
        name = "strong_stock_screen"

        def screen(self, frame):
            return _candidate_frame()

    monkeypatch.setattr(cli, "load_ohlcv_dataset", lambda *a, **k: pd.DataFrame({"symbol": ["000001"], "close": [10.0]}))
    monkeypatch.setattr(cli, "strategy_from_args", lambda _args: DummyStrategy())

    class ConstraintPolicy:
        def kwargs_for(self, _strategy):
            return {}

    monkeypatch.setattr(
        cli,
        "settings_from_args",
        lambda _args: SimpleNamespace(
            scoring=SimpleNamespace(weights={}),
            risk=SimpleNamespace(constraint_policy=ConstraintPolicy()),
        ),
    )

    cli.run_screen(args)

    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    assert bool(payload[0]["strategy_actionable"]) is False
    assert tracker.exists() is False


def _strategy_args(tmp_path, constraint_log):
    return Namespace(
        strategy="strong_stock_screen",
        settings=None,
        sqlite=None,
        tracker=tmp_path / "selections.jsonl",
        journal=tmp_path / "trades.jsonl",
        promotion_log=tmp_path / "promotions.jsonl",
        constraint_log=constraint_log,
        disable_approval_cooldown=True,
    )


def _candidate_frame():
    return pd.DataFrame(
        {
            "symbol": ["000001"],
            "name": ["Demo"],
            "score": [100.0],
            "risk_grade": ["medium"],
            "close": [10.0],
            "atr_stop_price": [9.0],
        }
    )


def _write_constraint(path, *, alert_level, action, exposure_multiplier, alerts):
    path.write_text(
        json.dumps(
            {
                "created_at": "2026-05-30T15:30:00+08:00",
                "source": "review.attribution",
                "strategy": "strong_stock_screen",
                "symbol": "",
                "alert_level": alert_level,
                "action": action,
                "alerts": alerts,
                "note": "Attribution policy test constraint.",
                "exposure_multiplier": exposure_multiplier,
                "effective_date": "2026-05-31",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
