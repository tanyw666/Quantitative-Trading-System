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
