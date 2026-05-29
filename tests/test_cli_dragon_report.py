from argparse import Namespace
import json

import pandas as pd

import quant_system.cli as cli


def test_run_dragon_validation_report_accepts_cached_dataset(tmp_path, monkeypatch):
    output = tmp_path / "dragon.md"
    tracker = tmp_path / "selections.jsonl"
    tracker.write_text(
        json.dumps(
            {
                "date": "2026-05-28",
                "strategy": "dragon_leader",
                "symbol": "000001",
                "name": "样例股",
                "close": 10.0,
                "entry_gate": "pass",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-05-28", "2026-05-29", "2026-05-28", "2026-05-29"]),
            "symbol": ["000001", "000001", "000002", "000002"],
            "open": [10, 10.5, 8, 8.1],
            "high": [10.8, 10.9, 8.2, 8.2],
            "low": [9.8, 10.2, 7.9, 8.0],
            "close": [10.0, 10.6, 8.0, 8.1],
            "volume": [1000, 1200, 800, 900],
            "name": ["样例股", "样例股", "备选股", "备选股"],
            "board": ["MAIN", "MAIN", "MAIN", "MAIN"],
        }
    )

    monkeypatch.setattr(cli, "load_ohlcv_dataset", lambda csv, cache_dir, universe: frame)
    monkeypatch.setattr(
        cli,
        "create_strategy",
        lambda *args, **kwargs: type("S", (), {"screen": lambda self, frame: pd.DataFrame([{"symbol": "000001", "name": "样例股", "close": 10.6, "entry_gate": "pass"}])})(),
    )
    monkeypatch.setattr(cli, "enrich_and_score_candidates", lambda frame, candidates, *args, **kwargs: candidates.assign(score=88.0, dragon_score=88.0, seal_quality_score=70.0, dragon_state="watch", dragon_tags="repair"))
    monkeypatch.setattr(cli, "settings_from_args", lambda args: type("Settings", (), {"scoring": type("Scoring", (), {"weights": {}})()})())
    monkeypatch.setattr(
        cli,
        "BacktestEngine",
        lambda config: type("E", (), {"run": lambda self, frame, strategy: type("R", (), {"summary": lambda self: {"total_return": 0.01, "final_equity": 101000, "max_drawdown": 0.02, "trades": 1, "win_rate": 1.0}})()})(),
    )

    args = Namespace(
        csv=None,
        cache_dir=tmp_path / "cache",
        universe=tmp_path / "universe.csv",
        tracker=tracker,
        horizons="1,3,5",
        cash=100000,
        buy_price="open",
        entry_gate="pass",
        dragon_entry_model="next-open",
        max_next_open_gap=0.07,
        min_next_open_gap=-0.03,
        allow_next_open_below_ma5=False,
        top=5,
        sector_column=None,
        sector_top=5,
        only_top_sectors=False,
        output=output,
    )

    cli.run_dragon_validation_report(args)

    content = output.read_text(encoding="utf-8")
    assert "龙头战法验证报告" in content
    assert "当前龙头候选" in content
    assert "样例股" in content
