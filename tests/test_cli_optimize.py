from argparse import Namespace
import json
from types import SimpleNamespace

import pytest

import quant_system.cli as cli
from quant_system.storage.sqlite_store import SQLiteStore


def test_validate_strategy_cli_exits_nonzero_on_bad_config(tmp_path, capsys):
    config = tmp_path / "bad.yaml"
    config.write_text("name: broken\n", encoding="utf-8")
    args = Namespace(config=config, csv=None)

    with pytest.raises(SystemExit) as exc:
        cli.run_optimize_validate_strategy(args)

    assert exc.value.code == 1
    assert '"ok": false' in capsys.readouterr().out


def test_validate_strategies_cli_exits_nonzero_when_any_config_fails(tmp_path, capsys):
    (tmp_path / "good.yaml").write_text("name: strong_stock_screen\n", encoding="utf-8")
    (tmp_path / "bad.yaml").write_text("name: broken\n", encoding="utf-8")
    args = Namespace(dir=tmp_path, csv=None)

    with pytest.raises(SystemExit) as exc:
        cli.run_optimize_validate_strategies(args)

    assert exc.value.code == 1
    assert '"ok": false' in capsys.readouterr().out


def test_review_promotions_cli_summarizes_history(tmp_path, capsys):
    log_path = tmp_path / "promotions.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "created_at": "2026-05-28T08:00:00+00:00",
                "output": "configs/strategies/promoted.yaml",
                "ok": True,
                "backtest_requested": True,
                "validation": {"smoke": {"rows": 3}},
                "backtest": {"total_return": 0.12, "sharpe": 1.8, "trades": 4},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(log=log_path, limit=10)

    cli.run_review_promotions(args)

    output = capsys.readouterr().out
    assert '"total": 1' in output
    assert '"best_backtest"' in output
    assert "promoted.yaml" in output


def test_review_promotions_cli_can_read_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_strategy_promotion(
        {
            "created_at": "2026-05-28T08:00:00+00:00",
            "output": "configs/strategies/promoted.yaml",
            "ok": True,
            "backtest_requested": True,
            "validation": {"smoke": {"rows": 3}},
            "backtest": {"total_return": 0.12, "sharpe": 1.8, "trades": 4},
        }
    )
    args = Namespace(log=tmp_path / "unused.jsonl", sqlite=sqlite_path, limit=10)

    cli.run_review_promotions(args)

    output = capsys.readouterr().out
    assert '"total": 1' in output
    assert "promoted.yaml" in output


def test_optimize_health_cli_reads_sqlite(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_selections(
        [
            {
                "date": "2026-05-29",
                "strategy": "dragon",
                "symbol": "000001",
                "name": "Demo",
                "close": 10,
                "reason": "test",
            }
        ]
    )
    store.insert_trade(
        {
            "date": "2026-05-29",
            "strategy": "dragon",
            "symbol": "000001",
            "side": "BUY",
            "price": 10,
            "quantity": 100,
            "reason": "buy",
            "amount": 1000,
        }
    )
    store.insert_strategy_promotion(
        {
            "created_at": "2026-05-29T08:00:00+00:00",
            "strategy_name": "dragon",
            "output": "configs/strategies/dragon.yaml",
            "ok": True,
            "backtest_requested": True,
            "backtest": {"total_return": 0.12, "sharpe": 1.8, "trades": 4},
        }
    )
    args = Namespace(sqlite=sqlite_path)

    cli.run_optimize_health(args)

    output = capsys.readouterr().out
    assert '"strategy": "dragon"' in output
    assert '"promotion_count": 1' in output
    assert '"status": "watch"' in output or '"status": "strong"' in output


def test_optimize_health_cli_applies_constraint_policy(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_selections(
        [
            {
                "date": "2026-05-29",
                "strategy": "dragon",
                "symbol": "000001",
                "name": "Demo",
                "close": 10,
                "reason": "test",
            }
        ]
    )
    store.insert_strategy_constraint(
        {
            "created_at": "2026-05-29T09:10:00+00:00",
            "source": "portfolio.precheck",
            "strategy": "dragon",
            "alert_level": "block",
            "action": "pause",
            "alerts": ["mistake_cluster"],
            "note": "demo",
        }
    )
    args = Namespace(sqlite=sqlite_path)

    cli.run_optimize_health(args)

    output = capsys.readouterr().out
    assert '"strategy": "dragon"' in output
    assert '"action": "pause"' in output
    assert '"policy_state": "blocked"' in output
    assert '"constraint_policy"' in output


def test_optimize_health_cli_uses_lifecycle_history_and_doctor_memory(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_selections(
        [
            {
                "date": "2026-05-29",
                "strategy": "dragon",
                "symbol": "000001",
                "name": "Demo",
                "close": 10,
                "reason": "test",
            }
        ]
    )
    store.insert_trade(
        {
            "date": "2026-05-30",
            "strategy": "dragon",
            "symbol": "000001",
            "side": "BUY",
            "price": 10,
            "quantity": 100,
            "amount": 1000,
        }
    )
    store.insert_position_action_plan(
        {
            "created_at": "2026-05-28T09:00:00+00:00",
            "action_date": "2026-05-28",
            "status": "warn",
            "reduce_count": 1,
            "actions": [],
        }
    )
    store.insert_exit_plan(
        {
            "created_at": "2026-05-29T10:00:00+00:00",
            "plan_date": "2026-05-29",
            "status": "warn",
            "sell_all_count": 1,
            "items": [],
        }
    )
    store.insert_lifecycle_snapshot(
        {
            "created_at": "2026-05-28T12:00:00+00:00",
            "snapshot_date": "2026-05-28",
            "status": "block",
            "execution": {
                "trade_plan_match_rate": 0.6,
                "action_execution_rate": 0.5,
                "exit_execution_rate": 0.0,
                "lot_exit_execution_rate": 0.0,
                "action_missed_count": 1,
                "exit_missed_count": 1,
                "lot_exit_missed_count": 1,
            },
            "exit_plan": {"sell_all_count": 1},
        }
    )
    store.insert_lifecycle_snapshot(
        {
            "created_at": "2026-05-29T12:00:00+00:00",
            "snapshot_date": "2026-05-29",
            "status": "block",
            "execution": {
                "trade_plan_match_rate": 0.5,
                "action_execution_rate": 0.0,
                "exit_execution_rate": 0.0,
                "lot_exit_execution_rate": 0.0,
                "action_missed_count": 1,
                "exit_missed_count": 1,
                "lot_exit_missed_count": 1,
            },
            "exit_plan": {"sell_all_count": 1},
        }
    )
    args = Namespace(sqlite=sqlite_path, settings=None)

    cli.run_optimize_health(args)

    output = capsys.readouterr().out
    assert '"strategy": "dragon"' in output
    assert '"action": "pause"' in output
    assert '"doctor_status": "warn"' in output
    assert '"block_count": 2' in output
    assert '"status_trend": "worsening"' in output


def test_optimize_validate_strategy_cli_accepts_trade_plan_log(tmp_path, capsys):
    config = tmp_path / "strategy.yaml"
    config.write_text(
        """
name: tuned
strategy: strong_stock_screen
""".strip(),
        encoding="utf-8",
    )
    trade_plan_log = tmp_path / "trade_plans.jsonl"
    trade_plan_log.write_text(
        json.dumps(
            {
                "trade_date": "2026-05-29",
                "strategy": "strong_stock_screen",
                "symbol": "000001",
                "entry_price": 10.0,
                "planned_pct": 0.1,
                "planned_value": 1000.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(config=config, csv=None, trade_plan_log=trade_plan_log)

    cli.run_optimize_validate_strategy(args)

    output = capsys.readouterr().out
    assert '"score":' in output
    assert '"alerts":' in output


def test_optimize_promote_strategy_cli_accepts_trade_plan_log(tmp_path, capsys):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "preferred_horizon": 1,
                "min_count": 1,
                "recommendation": {
                    "name": "balanced",
                    "strategy": "strong_stock_screen",
                    "params": {"min_20d_return": 0.1},
                    "score": 0.03,
                },
                "result_count": 1,
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "promoted.yaml"
    trade_plan_log = tmp_path / "trade_plans.jsonl"
    trade_plan_log.write_text(
        json.dumps(
            {
                "trade_date": "2026-05-29",
                "strategy": "strong_stock_screen",
                "symbol": "000001",
                "entry_price": 10.0,
                "planned_pct": 0.1,
                "planned_value": 1000.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        summary=summary_path,
        output=output_path,
        name=None,
        description=None,
        csv=None,
        backtest=False,
        buy_price="close",
        cash=100000,
        promotion_output=None,
        promotion_log=None,
        sqlite=None,
        trade_plan_log=trade_plan_log,
    )

    cli.run_optimize_promote_strategy(args)

    output = capsys.readouterr().out
    assert '"trade_plan_pressure"' in output
    assert '"trade_plan_score"' in output or '"score"' in output


def test_optimize_health_cli_respects_constraint_policy_settings(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        """
risk:
  constraint_policy:
    single_block_pause: 2
    cooldown_block_count: 2
""".strip(),
        encoding="utf-8",
    )
    store = SQLiteStore(sqlite_path)
    store.insert_selections(
        [
            {
                "date": "2026-05-29",
                "strategy": "dragon",
                "symbol": "000001",
                "name": "Demo",
                "close": 10,
                "reason": "test",
            }
        ]
    )
    store.insert_strategy_constraint(
        {
            "created_at": "2026-05-29T09:10:00+00:00",
            "source": "portfolio.precheck",
            "strategy": "dragon",
            "alert_level": "block",
            "action": "pause",
            "alerts": ["mistake_cluster"],
            "note": "demo",
        }
    )
    args = Namespace(sqlite=sqlite_path, settings=settings_path)

    cli.run_optimize_health(args)

    output = capsys.readouterr().out
    assert '"policy_state": "normal"' in output
    assert '"action": "pause"' not in output


def test_settings_from_args_preserves_constraint_policy_and_data_sources(tmp_path):
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        """
data_sources:
  daily_source: tencent
risk:
  constraint_policy:
    recover_after_clean_days: 4
scoring:
  weights:
    momentum_20: 0.4
""".strip(),
        encoding="utf-8",
    )
    args = Namespace(settings=settings_path, _resolved_strategy=SimpleNamespace(scoring_weights={"momentum_20": 0.7}))

    settings = cli.settings_from_args(args)

    assert settings.scoring.weights["momentum_20"] == 0.7
    assert settings.risk.constraint_policy.recover_after_clean_days == 4
    assert settings.data_sources.daily_source == "tencent"


def test_settings_from_args_merges_strategy_constraint_policy(tmp_path):
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        """
risk:
  constraint_policy:
    recover_after_clean_days: 3
""".strip(),
        encoding="utf-8",
    )
    args = Namespace(
        settings=settings_path,
        _resolved_strategy=SimpleNamespace(
            scoring_weights={},
            constraint_policy={"window_days": 7, "single_block_pause": 2},
        ),
    )

    settings = cli.settings_from_args(args)

    assert settings.risk.constraint_policy.window_days == 7
    assert settings.risk.constraint_policy.single_block_pause == 2
    assert settings.risk.constraint_policy.recover_after_clean_days == 3


def test_optimize_health_cli_applies_strategy_specific_constraint_policy(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        """
risk:
  constraint_policy:
    single_block_pause: 2
    strategies:
      dragon_leader:
        single_block_pause: 1
        recover_after_clean_days: 5
""".strip(),
        encoding="utf-8",
    )
    store = SQLiteStore(sqlite_path)
    for strategy in ["dragon_leader", "strong_stock_screen"]:
        store.insert_selections(
            [
                {
                    "date": "2026-05-29",
                    "strategy": strategy,
                    "symbol": "000001",
                    "name": "Demo",
                    "close": 10,
                    "reason": "test",
                }
            ]
        )
        store.insert_strategy_constraint(
            {
                "created_at": "2026-05-29T09:10:00+00:00",
                "source": "portfolio.precheck",
                "strategy": strategy,
                "alert_level": "block",
                "action": "pause",
                "alerts": ["mistake_cluster"],
                "note": "demo",
            }
        )
    args = Namespace(sqlite=sqlite_path, settings=settings_path)

    cli.run_optimize_health(args)

    output = capsys.readouterr().out
    assert '"strategy": "dragon_leader"' in output
    assert '"policy_state": "blocked"' in output
    assert "连续5日" in output
    assert '"strategy": "strong_stock_screen"' in output
    assert '"policy_state": "normal"' in output


def test_optimize_rotation_cli_outputs_strategy_ranking(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_selections(
        [
            {"date": "2026-05-29", "strategy": "dragon", "symbol": "000001", "close": 10, "reason": "test"},
            {"date": "2026-05-29", "strategy": "reversal", "symbol": "000002", "close": 8, "reason": "test"},
        ]
    )
    store.insert_trade(
        {
            "date": "2026-05-29",
            "strategy": "dragon",
            "symbol": "000001",
            "side": "BUY",
            "amount": 1000,
            "tags": ["计划内"],
        }
    )
    store.insert_strategy_constraint(
        {
            "created_at": "2026-05-29T09:10:00+00:00",
            "source": "portfolio.precheck",
            "strategy": "reversal",
            "alert_level": "block",
            "action": "pause",
            "alerts": ["mistake_cluster"],
            "note": "demo",
        }
    )
    args = Namespace(
        sqlite=sqlite_path,
        settings=None,
        promotion_log=tmp_path / "unused.jsonl",
        constraint_log=tmp_path / "unused_constraints.jsonl",
        limit=5,
        format="json",
    )

    cli.run_optimize_rotation(args)

    output = capsys.readouterr().out
    assert '"count": 2' in output
    assert '"strategy": "dragon"' in output
    assert '"strategy": "reversal"' in output
    assert '"priority": "暂停"' in output


def test_optimize_rotation_cli_can_output_markdown(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    SQLiteStore(sqlite_path).insert_selections(
        [{"date": "2026-05-29", "strategy": "dragon", "symbol": "000001", "close": 10, "reason": "test"}]
    )
    args = Namespace(
        sqlite=sqlite_path,
        settings=None,
        promotion_log=tmp_path / "unused.jsonl",
        constraint_log=tmp_path / "unused_constraints.jsonl",
        limit=5,
        format="markdown",
    )

    cli.run_optimize_rotation(args)

    output = capsys.readouterr().out
    assert "| 策略 | 轮换分" in output
    assert "当前主线建议" in output


def test_optimize_rotation_cli_writes_output_and_snapshot(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    output_path = tmp_path / "rotation.json"
    snapshot_dir = tmp_path / "snapshots"
    SQLiteStore(sqlite_path).insert_selections(
        [{"date": "2026-05-29", "strategy": "dragon", "symbol": "000001", "close": 10, "reason": "test"}]
    )
    args = Namespace(
        sqlite=sqlite_path,
        settings=None,
        promotion_log=tmp_path / "unused.jsonl",
        constraint_log=tmp_path / "unused_constraints.jsonl",
        limit=5,
        format="json",
        output=output_path,
        snapshot_dir=snapshot_dir,
    )

    cli.run_optimize_rotation(args)

    output = capsys.readouterr().out
    snapshots = list(snapshot_dir.glob("rotation_*.json"))
    assert output_path.exists()
    assert snapshots
    assert '"created_at"' in output_path.read_text(encoding="utf-8")
    assert str(output_path) in output


def test_optimize_rotation_history_cli_outputs_summary_and_writes_file(tmp_path, capsys):
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    (snapshot_dir / "rotation_20260528T090000.json").write_text(
        json.dumps(
            {
                "created_at": "2026-05-28T09:00:00+00:00",
                "count": 1,
                "items": [{"strategy": "dragon", "rotation_score": 70, "priority": "观察", "action": "确认单"}],
            }
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "rotation_20260529T090000.json").write_text(
        json.dumps(
            {
                "created_at": "2026-05-29T09:00:00+00:00",
                "count": 1,
                "items": [{"strategy": "dragon", "rotation_score": 86, "priority": "主打", "action": "主策略"}],
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "rotation_history.md"
    args = Namespace(snapshot_dir=snapshot_dir, limit=20, format="markdown", output=output_path)

    cli.run_optimize_rotation_history(args)

    output = capsys.readouterr().out
    assert "快照数量：2" in output
    assert "走强" in output
    assert output_path.exists()


def test_daily_weekly_briefing_accept_rotation_snapshot_dir(tmp_path):
    args_daily = cli.build_parser().parse_args(["report", "daily", "--rotation-snapshot-dir", str(tmp_path)])
    args_weekly = cli.build_parser().parse_args(["report", "weekly", "--rotation-snapshot-dir", str(tmp_path)])
    args_briefing = cli.build_parser().parse_args(["report", "briefing", "--csv", "prices.csv", "--rotation-snapshot-dir", str(tmp_path)])

    assert args_daily.rotation_snapshot_dir == tmp_path
    assert args_weekly.rotation_snapshot_dir == tmp_path
    assert args_briefing.rotation_snapshot_dir == tmp_path


def test_briefing_cli_includes_promotion_history(tmp_path, capsys):
    promotion_log = tmp_path / "promotions.jsonl"
    promotion_log.write_text(
        json.dumps(
            {
                "created_at": "2026-05-28T09:00:55+00:00",
                "output": "configs/strategies/promoted.yaml",
                "ok": True,
                "backtest_requested": True,
                "validation": {"smoke": {"rows": 1}},
                "backtest": {"total_return": 0.05, "sharpe": 1.2, "trades": 3},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(log=promotion_log, limit=10)

    # reuse the reporting summarizer directly through the briefing input path
    from quant_system.reports.briefing import BriefingInput, BriefingReport

    content = BriefingReport().render(
        BriefingInput(
            title="简报",
            market_temperature={"score": 50, "regime": "warm", "stance": "观察", "advance_ratio": 0.5, "above_ma20_ratio": 0.5},
            candidates=[],
            allocation_plan={"target_exposure_pct": 0, "allocated_pct": 0, "items": []},
            position_book={"total_market_value": 0, "total_unrealized_pnl": 0, "total_exposure_pct": 0, "positions": []},
            holding_risk={"status": "pass", "checks": []},
            promotion_summary={"total": 1, "ok_count": 1, "failed_count": 0, "backtest_count": 1, "latest_created_at": "2026-05-28T09:00:55+00:00", "best_backtest": {"output": "configs/strategies/promoted.yaml", "total_return": 0.05, "sharpe": 1.2, "trades": 3}, "records": [{"created_at": "2026-05-28T09:00:55+00:00", "output": "configs/strategies/promoted.yaml", "ok": True, "total_return": 0.05, "sharpe": 1.2}]},
        )
    )

    assert "策略晋升" in content
    assert "promoted.yaml" in content


def test_optimize_health_cli_combines_trade_plan_jsonl(tmp_path, capsys):
    selection_log = tmp_path / "selections.jsonl"
    trade_log = tmp_path / "trades.jsonl"
    plan_log = tmp_path / "trade_plans.jsonl"

    selection_log.write_text(
        json.dumps({"date": "2026-05-29", "strategy": "dragon", "symbol": "000001", "close": 10, "reason": "test"}) + "\n",
        encoding="utf-8",
    )
    trade_log.write_text(
        json.dumps({"date": "2026-05-29", "strategy": "dragon", "symbol": "000001", "side": "BUY", "price": 10.2, "quantity": 100, "amount": 1020, "execution_deviation_pct": 0.02}) + "\n",
        encoding="utf-8",
    )
    plan_log.write_text(
        json.dumps({"trade_date": "2026-05-29", "strategy": "dragon", "symbol": "000001", "entry_price": 10.0, "planned_pct": 0.1, "planned_value": 1000.0, "status": "pass", "gate_status": "pass"}) + "\n"
        + json.dumps({"trade_date": "2026-05-29", "strategy": "dragon", "symbol": "000002", "entry_price": 11.0, "planned_pct": 0.1, "planned_value": 1000.0, "status": "warn", "gate_status": "warn"}) + "\n",
        encoding="utf-8",
    )

    args = Namespace(
        tracker=selection_log,
        journal=trade_log,
        log=plan_log,
        sqlite=None,
        promotion_log=tmp_path / "promotions.jsonl",
        constraint_log=tmp_path / "constraints.jsonl",
        settings=None,
    )

    cli.run_optimize_health(args)

    output = capsys.readouterr().out
    assert '"strategy": "dragon"' in output
    assert '"trade_plan_match_rate"' in output
    assert '"trade_plan_unmatched_count"' in output


def test_optimize_rotation_cli_carries_trade_plan_signals_into_snapshot(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    snapshot_dir = tmp_path / "snapshots"
    store = SQLiteStore(sqlite_path)
    store.insert_selections(
        [
            {
                "date": "2026-05-29",
                "strategy": "dragon",
                "symbol": "000001",
                "name": "Demo",
                "close": 10,
                "reason": "test",
            }
        ]
    )
    store.insert_trade(
        {
            "date": "2026-05-29",
            "strategy": "dragon",
            "symbol": "000001",
            "side": "BUY",
            "price": 10.5,
            "quantity": 100,
            "amount": 1050,
        }
    )
    store.insert_trade(
        {
            "date": "2026-05-29",
            "strategy": "dragon",
            "symbol": "000002",
            "side": "BUY",
            "price": 11.0,
            "quantity": 100,
            "amount": 1100,
        }
    )
    store.insert_strategy_promotion(
        {
            "created_at": "2026-05-29T08:00:00+00:00",
            "strategy_name": "dragon",
            "output": "configs/strategies/dragon.yaml",
            "ok": True,
            "backtest_requested": True,
            "backtest": {"total_return": 0.12, "sharpe": 1.8, "trades": 4},
        }
    )
    store.insert_strategy_constraint(
        {
            "created_at": "2026-05-29T09:10:00+00:00",
            "source": "portfolio.precheck",
            "strategy": "dragon",
            "alert_level": "warn",
            "action": "reduce",
            "alerts": ["execution_deviation"],
            "note": "demo",
        }
    )

    args = Namespace(
        sqlite=sqlite_path,
        settings=None,
        promotion_log=tmp_path / "unused_promotions.jsonl",
        constraint_log=tmp_path / "unused_constraints.jsonl",
        limit=5,
        format="json",
        output=None,
        snapshot_dir=snapshot_dir,
    )

    cli.run_optimize_rotation(args)

    output = capsys.readouterr().out
    snapshot_files = list(snapshot_dir.glob("rotation_*.json"))
    assert snapshot_files
    assert '"trade_plan_match_rate"' in output or '"trade_plan_match_rate"' in snapshot_files[0].read_text(encoding="utf-8")


def test_optimize_rotation_cli_inherits_review_memory_pressure(tmp_path, capsys):
    sqlite_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(sqlite_path)
    store.insert_selections(
        [{"date": "2026-05-29", "strategy": "dragon", "symbol": "000001", "close": 10, "reason": "test"}]
    )
    store.insert_trade(
        {
            "date": "2026-05-30",
            "strategy": "dragon",
            "symbol": "000001",
            "side": "BUY",
            "amount": 1000,
        }
    )
    store.insert_position_action_plan(
        {
            "created_at": "2026-05-29T10:00:00+00:00",
            "action_date": "2026-05-29",
            "status": "warn",
            "reduce_count": 1,
            "actions": [],
        }
    )
    store.insert_exit_plan(
        {
            "created_at": "2026-05-29T11:00:00+00:00",
            "plan_date": "2026-05-29",
            "status": "warn",
            "sell_all_count": 1,
            "items": [],
        }
    )
    for day in ("2026-05-28", "2026-05-29"):
        store.insert_lifecycle_snapshot(
            {
                "created_at": f"{day}T12:00:00+00:00",
                "snapshot_date": day,
                "status": "block",
                "execution": {
                    "trade_plan_match_rate": 0.5,
                    "action_execution_rate": 0.0,
                    "exit_execution_rate": 0.0,
                    "lot_exit_execution_rate": 0.0,
                    "action_missed_count": 1,
                    "exit_missed_count": 1,
                    "lot_exit_missed_count": 1,
                },
                "exit_plan": {"sell_all_count": 1},
            }
        )
    args = Namespace(
        sqlite=sqlite_path,
        settings=None,
        promotion_log=tmp_path / "unused_promotions.jsonl",
        constraint_log=tmp_path / "unused_constraints.jsonl",
        limit=5,
        format="json",
    )

    cli.run_optimize_rotation(args)

    output = capsys.readouterr().out
    assert '"strategy": "dragon"' in output
    assert '"priority": "暂停"' in output


def test_optimize_validate_strategy_cli_accepts_trade_plan_log(tmp_path, capsys):
    config = tmp_path / "strategy.yaml"
    config.write_text(
        """
name: tuned
strategy: strong_stock_screen
""".strip(),
        encoding="utf-8",
    )
    trade_plan_log = tmp_path / "trade_plans.jsonl"
    trade_plan_log.write_text(
        json.dumps(
            {
                "trade_date": "2026-05-29",
                "strategy": "strong_stock_screen",
                "symbol": "000001",
                "entry_price": 10.0,
                "planned_pct": 0.1,
                "planned_value": 1000.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(config=config, csv=None, trade_plan_log=trade_plan_log)

    cli.run_optimize_validate_strategy(args)

    output = capsys.readouterr().out
    assert '"score":' in output
    assert '"alerts":' in output


def test_optimize_promote_strategy_cli_accepts_trade_plan_log(tmp_path, capsys):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "preferred_horizon": 1,
                "min_count": 1,
                "recommendation": {
                    "name": "balanced",
                    "strategy": "strong_stock_screen",
                    "params": {"min_20d_return": 0.1},
                    "score": 0.03,
                },
                "result_count": 1,
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "promoted.yaml"
    trade_plan_log = tmp_path / "trade_plans.jsonl"
    trade_plan_log.write_text(
        json.dumps(
            {
                "trade_date": "2026-05-29",
                "strategy": "strong_stock_screen",
                "symbol": "000001",
                "entry_price": 10.0,
                "planned_pct": 0.1,
                "planned_value": 1000.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    args = Namespace(
        summary=summary_path,
        output=output_path,
        name=None,
        description=None,
        csv=None,
        backtest=False,
        buy_price="close",
        cash=100000,
        promotion_output=None,
        promotion_log=None,
        sqlite=None,
        trade_plan_log=trade_plan_log,
    )

    cli.run_optimize_promote_strategy(args)

    output = capsys.readouterr().out
    assert '"trade_plan_pressure"' in output
    assert '"trade_plan_score"' in output or '"score"' in output
