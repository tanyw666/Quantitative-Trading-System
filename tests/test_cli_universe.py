from argparse import Namespace
import json

import pandas as pd

import quant_system.cli as cli


def test_data_universe_falls_back_to_existing_output_when_remote_fails(tmp_path, monkeypatch, capsys):
    output = tmp_path / "universe.csv"
    output.write_text("symbol,name\n000001,Demo\n", encoding="utf-8")

    calls = {"count": 0}

    def fail_fetch():
        calls["count"] += 1
        return pd.DataFrame({"symbol": ["000001"], "name": ["Demo"]})

    monkeypatch.setattr(cli, "fetch_akshare_universe_with_retry", fail_fetch)
    args = Namespace(
        input=None,
        output=output,
        source="akshare",
        include_st=False,
        include_bj=False,
        exclude_star=False,
        exclude_chinext=False,
        min_list_days=None,
    )

    cli.run_data_universe(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] in {"ok", "fallback_cached"}
    assert payload["rows"] == 1
    assert calls["count"] == 1


def test_data_universe_builds_real_universe_from_named_sources(tmp_path, monkeypatch, capsys):
    def fake_fetch():
        return pd.DataFrame({"code": ["000001", "600000"], "name": ["平安银行", "浦发银行"]})

    monkeypatch.setattr(cli, "fetch_akshare_universe_with_retry", fake_fetch)

    args = Namespace(
        input=None,
        output=tmp_path / "universe.csv",
        source="akshare",
        include_st=False,
        include_bj=False,
        exclude_star=False,
        exclude_chinext=False,
        min_list_days=None,
    )

    cli.run_data_universe(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["rows"] == 2


def test_data_universe_supports_full_a_share_like_codes():
    from quant_system.data.universe_builder import filter_universe, UniverseBuildOptions

    frame = pd.DataFrame(
        {
            "code": ["000001", "300001", "688001", "430001", "600001"],
            "name": ["平安银行", "特锐德", "华兴源创", "北交所示例", "上汽集团"],
        }
    )

    filtered = filter_universe(
        frame,
        UniverseBuildOptions(include_st=True, include_bj=True, include_star=True, include_chinext=True),
    )

    assert set(filtered["board"]) >= {"MAIN", "CHINEXT", "STAR", "BSE"}
    assert filtered["symbol"].tolist() == ["000001", "300001", "430001", "600001", "688001"]
