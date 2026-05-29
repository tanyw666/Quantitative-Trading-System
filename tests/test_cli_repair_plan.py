from argparse import Namespace
import json

import pandas as pd

import quant_system.cli as cli


def test_run_data_repair_plan_outputs_priority_symbols(monkeypatch, capsys):
    frame = pd.DataFrame(
        {
            "date": ["2026-04-20", "2026-05-28"],
            "symbol": ["688121", "000001"],
            "name": ["卓然股份", "正常股票"],
            "open": [10, 10],
            "high": [11, 11],
            "low": [9, 9],
            "close": [10, 10],
            "volume": [1000, 1000],
        }
    )
    monkeypatch.setattr(cli, "load_ohlcv_dataset", lambda *args, **kwargs: frame)

    cli.run_data_repair_plan(
        Namespace(
            csv=None,
            cache_dir=None,
            universe=None,
            strict=False,
            min_rows=1,
            max_stale_days=10,
            as_of="2026-05-29",
        )
    )

    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "action_needed"
    assert payload["priority_symbols"] == ["688121"]


def test_run_data_repair_execute_dry_run_does_not_fetch(monkeypatch, capsys, tmp_path):
    frame = pd.DataFrame(
        {
            "date": ["2026-04-20", "2026-05-28"],
            "symbol": ["688121", "000001"],
            "name": ["卓然股份", "正常股票"],
            "open": [10, 10],
            "high": [11, 11],
            "low": [9, 9],
            "close": [10, 10],
            "volume": [1000, 1000],
        }
    )
    monkeypatch.setattr(cli, "load_ohlcv_dataset", lambda *args, **kwargs: frame)
    calls = {"fetch": 0}
    monkeypatch.setattr(cli, "fetch_daily_to_cache", lambda *args, **kwargs: calls.__setitem__("fetch", calls["fetch"] + 1))

    cli.run_data_repair_execute(
        Namespace(
            csv=None,
            cache_dir=tmp_path / "cache",
            universe=None,
            strict=False,
            min_rows=1,
            max_stale_days=10,
            as_of="2026-05-29",
            start=None,
            end=None,
            adjust="qfq",
            source="auto",
            limit=None,
            execute=False,
        )
    )

    payload = json.loads(capsys.readouterr().out)

    assert payload["mode"] == "dry-run"
    assert payload["targets"] == ["688121"]
    assert calls["fetch"] == 0


def test_run_data_repair_execute_fetches_when_execute(monkeypatch, capsys, tmp_path):
    frame = pd.DataFrame(
        {
            "date": ["2026-04-20", "2026-05-28"],
            "symbol": ["688121", "000001"],
            "name": ["卓然股份", "正常股票"],
            "open": [10, 10],
            "high": [11, 11],
            "low": [9, 9],
            "close": [10, 10],
            "volume": [1000, 1000],
        }
    )
    monkeypatch.setattr(cli, "load_ohlcv_dataset", lambda *args, **kwargs: frame)
    fetched: list[str] = []

    def fake_fetch_daily_to_cache(symbol, start_date, end_date, cache_dir, adjust, source):
        fetched.append(symbol)
        return cache_dir / symbol

    monkeypatch.setattr(cli, "fetch_daily_to_cache", fake_fetch_daily_to_cache)

    cli.run_data_repair_execute(
        Namespace(
            csv=None,
            cache_dir=tmp_path / "cache",
            universe=None,
            strict=False,
            min_rows=1,
            max_stale_days=10,
            as_of="2026-05-29",
            start="20250101",
            end="20260529",
            adjust="qfq",
            source="auto",
            limit=None,
            execute=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)

    assert payload["mode"] == "execute"
    assert fetched == ["688121"]
    assert payload["items"][0]["status"] == "ok"
