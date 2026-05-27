from argparse import Namespace
import json

import quant_system.cli as cli


def test_data_universe_falls_back_to_existing_output_when_remote_fails(tmp_path, monkeypatch, capsys):
    output = tmp_path / "universe.csv"
    output.write_text("symbol,name\n000001,Demo\n", encoding="utf-8")

    def fail_fetch():
        raise RuntimeError("remote disconnected")

    monkeypatch.setattr(cli, "fetch_akshare_universe", fail_fetch)
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
    assert payload["status"] == "fallback_cached"
    assert payload["rows"] == 1
    assert "remote disconnected" in payload["fallback_error"]
