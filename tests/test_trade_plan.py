from argparse import Namespace
import json

import pandas as pd

import quant_system.cli as cli
from quant_system.risk.pretrade import run_pretrade_check
from quant_system.risk.sizing import build_allocation_plan
from quant_system.portfolio.trade_plan import (
    append_unique_trade_plan_records,
    build_trade_plan,
    build_trade_plan_batch,
    render_trade_plan_markdown,
)
from quant_system.portfolio.trade_plan_audit import summarize_trade_plan_audit


def _candidates():
    return pd.DataFrame(
        {
            "symbol": ["000001"],
            "name": ["Demo"],
            "score": [100],
            "risk_grade": ["low"],
            "atr_stop_price": [9.0],
            "reason": ["breakout"],
        }
    )


def test_build_trade_plan_includes_pretrade_and_allocation_fields():
    candidates = _candidates()
    temperature = {"regime": "warm", "stance": "watch"}
    allocation_plan = build_allocation_plan(
        candidates,
        temperature,
        cash=100000,
        max_positions=1,
        regime_exposure={"warm": 0.3},
        cap_by_risk={"low": 0.2, "unknown": 0.05},
    )
    pretrade = run_pretrade_check(
        candidates,
        temperature,
        symbol="000001",
        entry_price=10.0,
        planned_pct=0.1,
        cash=100000,
        stop_price=9.0,
        target_price=12.0,
        max_positions=1,
        regime_exposure={"warm": 0.3},
        cap_by_risk={"low": 0.2, "unknown": 0.05},
    )

    plan = build_trade_plan(
        symbol="000001",
        trade_date="2026-05-29",
        pretrade_result=pretrade,
        allocation_plan=allocation_plan,
    )

    payload = plan.to_dict()
    assert payload["symbol"] == "000001"
    assert payload["status"] == "pass"
    assert payload["gate_status"] == "pass"
    assert payload["planned_pct"] > 0
    assert payload["items"][0]["symbol"] == "000001"


def test_render_trade_plan_markdown_includes_checklist():
    candidates = _candidates()
    temperature = {"regime": "warm", "stance": "watch"}
    allocation_plan = build_allocation_plan(
        candidates,
        temperature,
        cash=100000,
        max_positions=1,
        regime_exposure={"warm": 0.3},
        cap_by_risk={"low": 0.2, "unknown": 0.05},
    )
    pretrade = run_pretrade_check(
        candidates,
        temperature,
        symbol="000001",
        entry_price=10.0,
        planned_pct=0.1,
        cash=100000,
        stop_price=9.0,
        target_price=12.0,
        max_positions=1,
        regime_exposure={"warm": 0.3},
        cap_by_risk={"low": 0.2, "unknown": 0.05},
    )
    plan = build_trade_plan(
        symbol="000001",
        trade_date="2026-05-29",
        pretrade_result=pretrade,
        allocation_plan=allocation_plan,
    )

    content = render_trade_plan_markdown(plan)
    assert "# 交易计划 000001" in content
    assert "检查项" in content
    assert "动作清单" in content


def test_trade_plan_parser_and_trade_add_can_use_plan(tmp_path, capsys):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "planned_pct": 0.08,
                "entry_price": 10.0,
                "stop_price": 9.5,
                "target_price": 12.0,
                "gate_status": "warn",
                "gate_reason": "planned confirmation only",
                "discipline_exception": True,
                "exception_reason": "approved exception",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = Namespace(
        journal=tmp_path / "trades.jsonl",
        sqlite=None,
        date="2026-05-29",
        symbol="000001",
        side="BUY",
        price=10.5,
        quantity=100,
        reason="test",
        name="Demo",
        strategy="strong_stock_screen",
        market_regime="warm",
        planned_pct=0.1,
        actual_pct=0.1,
        planned_price=9.8,
        stop_price=9.0,
        target_price=12.0,
        tags="plan",
        mistake_type="",
        review="",
        workflow_summary=None,
        trade_plan=plan_path,
        gate_status="",
        gate_message="",
        gate_reason=[],
        discipline_exception=False,
        exception_reason="",
    )

    cli.run_review_trade_add(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["planned_pct"] == 0.08
    assert payload["planned_price"] == 10.0
    assert payload["gate_status"] == "warn"
    assert payload["discipline_exception"] is True
    assert "trade-plan" in payload["tags"]


def test_portfolio_plan_can_record_jsonl(tmp_path, monkeypatch, capsys):
    log_path = tmp_path / "trade_plans.jsonl"

    class DummyStrategy:
        name = "strong_stock_screen"

        def screen(self, frame):
            return _candidates()

    class DummyTemperature:
        def to_dict(self):
            return {"regime": "warm", "stance": "watch"}

    class DummyPlan:
        strategy_constraint = {"strategy": "strong_stock_screen"}

        def to_dict(self):
            return {
                "symbol": "000001",
                "planned_pct": 0.08,
                "entry_price": 10.0,
                "gate_status": "pass",
            }

    monkeypatch.setattr(cli, "load_ohlcv_dataset", lambda *args, **kwargs: pd.DataFrame({"symbol": ["000001"]}))
    monkeypatch.setattr(cli, "strategy_from_args", lambda args: DummyStrategy())
    monkeypatch.setattr(
        cli,
        "settings_from_args",
        lambda args: Namespace(
            scoring=Namespace(weights={}),
            risk=Namespace(regime_exposure={"warm": 0.3}, cap_by_risk={"low": 0.2, "unknown": 0.05}),
        ),
    )
    monkeypatch.setattr(cli, "enrich_and_score_candidates", lambda *args, **kwargs: _candidates())
    monkeypatch.setattr(cli, "calculate_market_temperature", lambda *args, **kwargs: DummyTemperature())
    monkeypatch.setattr(cli, "_current_strategy_health", lambda args: {})
    monkeypatch.setattr(
        cli,
        "build_allocation_plan",
        lambda *args, **kwargs: Namespace(
            items=[],
            regime="warm",
            stance="watch",
            strategy_constraint={"strategy": "strong_stock_screen"},
            to_dict=lambda: {"items": []},
        ),
    )
    monkeypatch.setattr(
        cli,
        "run_pretrade_check",
        lambda *args, **kwargs: Namespace(
            symbol="000001",
            status="pass",
            planned_pct=0.08,
            planned_value=8000.0,
            allowed_pct=0.08,
            allowed_value=8000.0,
            entry_price=10.0,
            stop_price=9.5,
            target_price=12.0,
            stop_loss_pct=0.05,
            reward_risk=2.0,
            max_loss_value=500.0,
            expected_reward_value=1600.0,
            candidate_snapshot={"name": "Demo", "risk_grade": "low", "reason": "breakout"},
            checks=[],
            action_items=["review"],
        ),
    )
    monkeypatch.setattr(cli, "build_trade_plan", lambda **kwargs: DummyPlan())
    monkeypatch.setattr(cli, "persist_constraint_audit", lambda *args, **kwargs: None)

    args = Namespace(
        csv=tmp_path / "data.csv",
        cache_dir=None,
        universe=None,
        strategy="strong_stock_screen",
        config=None,
        settings=None,
        sqlite=None,
        constraint_log=tmp_path / "constraints.jsonl",
        cash=100000,
        top=5,
        symbol="000001",
        entry_price=10.0,
        planned_pct=0.08,
        stop_price=9.5,
        target_price=12.0,
        trade_date="2026-05-29",
        format="json",
        output=None,
        log=log_path,
        record=True,
        discipline_exception=False,
        exception_reason="",
        sector_column=None,
        sector_top=5,
        only_top_sectors=False,
    )

    cli.run_portfolio_plan(args)

    out = json.loads(capsys.readouterr().out)
    assert out["symbol"] == "000001"
    assert log_path.exists()
    saved = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert saved["symbol"] == "000001"
    assert saved["planned_pct"] == 0.08


def test_trade_plan_audit_matches_plan_and_trade(tmp_path):
    plan_records = [
        {
            "trade_date": "2026-05-29",
            "symbol": "000001",
            "planned_pct": 0.08,
            "planned_value": 8000.0,
            "entry_price": 10.0,
            "status": "pass",
            "gate_status": "pass",
        }
    ]
    trade_records = [
        {
            "date": "2026-05-29",
            "symbol": "000001",
            "side": "BUY",
            "price": 10.2,
            "quantity": 800,
            "amount": 8160.0,
            "planned_pct": 0.08,
            "planned_price": 10.0,
            "gate_status": "pass",
            "tags": ["trade-plan"],
        }
    ]

    summary = summarize_trade_plan_audit(plan_records, trade_records, limit=5)

    assert summary["total_plans"] == 1
    assert summary["matched_trades"] == 1
    assert summary["unmatched_plans"] == 0
    assert summary["orphan_trades"] == 0
    assert summary["match_rate"] == 1.0


def test_trade_plan_batch_blocks_when_strategy_is_paused():
    candidates = pd.DataFrame(
        {
            "symbol": ["000001"],
            "name": ["Demo"],
            "score": [100],
            "risk_grade": ["low"],
            "close": [10.0],
            "atr_stop_price": [9.0],
        }
    )

    batch = build_trade_plan_batch(
        candidates=candidates,
        market_temperature={"regime": "warm", "stance": "watch"},
        cash=100000,
        max_positions=1,
        strategy_health={"strategy": "strong_stock_screen", "alert_level": "block", "action": "pause"},
        trade_date="2026-05-30",
    )

    assert batch.total_plans == 0
    assert batch.status == "block"
    assert batch.gate_status == "block"


def test_append_unique_trade_plan_records_skips_repeat_runs(tmp_path):
    log_path = tmp_path / "trade_plans.jsonl"
    plan = {
        "created_at": "2026-05-30T01:00:00+00:00",
        "trade_date": "2026-05-30",
        "symbol": "000001",
        "strategy": "strong_stock_screen",
        "status": "pass",
        "gate_status": "pass",
        "planned_pct": 0.1,
        "entry_price": 10.0,
    }
    rerun_plan = {**plan, "created_at": "2026-05-30T02:00:00+00:00"}

    first = append_unique_trade_plan_records(log_path, [plan])
    second = append_unique_trade_plan_records(log_path, [rerun_plan])

    assert first == {"persisted_count": 1, "skipped_existing_count": 0}
    assert second == {"persisted_count": 0, "skipped_existing_count": 1}
    assert len(log_path.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_review_trade_audit_cli_uses_explicit_plan_log(tmp_path, capsys):
    plan_log = tmp_path / "trade_plans.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    plan_log.write_text(
        json.dumps(
            {
                "trade_date": "2026-05-29",
                "symbol": "000001",
                "planned_pct": 0.08,
                "planned_value": 8000.0,
                "entry_price": 10.0,
                "status": "pass",
                "gate_status": "pass",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    trade_log.write_text(
        json.dumps(
            {
                "date": "2026-05-29",
                "symbol": "000001",
                "side": "BUY",
                "price": 10.2,
                "quantity": 800,
                "amount": 8160.0,
                "planned_pct": 0.08,
                "planned_price": 10.0,
                "gate_status": "pass",
                "tags": ["trade-plan"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cli.run_review_trade_audit(Namespace(plan_log=plan_log, journal=trade_log, sqlite=None, limit=5, format="json", output=None))

    output = capsys.readouterr().out
    assert '"total_plans": 1' in output
    assert '"match_rate": 1.0' in output
