from pathlib import Path

from quant_system.data.universe import read_universe


def test_read_universe_accepts_code_column(tmp_path: Path):
    path = tmp_path / "universe.csv"
    path.write_text("code,name\n1,Demo\n", encoding="utf-8")

    stocks = read_universe(path)

    assert stocks[0].symbol == "000001"
    assert stocks[0].name == "Demo"


def test_read_universe_ignores_missing_metadata(tmp_path: Path):
    path = tmp_path / "universe.csv"
    path.write_text("symbol,name,industry,board\n000001,Demo,,\n", encoding="utf-8")

    stocks = read_universe(path)

    assert stocks[0].industry == ""
    assert stocks[0].board == ""
