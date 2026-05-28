from argparse import Namespace
import json

import pytest

import quant_system.cli as cli


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
