from argparse import Namespace

import pandas as pd

import quant_system.cli as cli
from quant_system.data.providers import ProviderResult
from quant_system.storage.sqlite_store import SQLiteStore


def test_sqlite_store_tracks_daily_and_minute_catalog(tmp_path):
    db_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(db_path)
    store.init()
    store.upsert_universe(pd.DataFrame({"symbol": ["000001"], "name": ["Demo"], "market": ["SZ"], "board": ["MAIN"]}))
    store.upsert_daily_bars(
        pd.DataFrame(
            {
                "symbol": ["000001"],
                "date": ["2024-01-02"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.5],
                "close": [10.5],
                "volume": [1000],
                "pre_close": [9.8],
                "pct_change": [0.0714],
                "turnover_rate": [1.2],
            }
        ),
        source="test",
        adjust="qfq",
    )
    store.upsert_minute_bar_catalog(
        {
            "symbol": "000001",
            "period": "1",
            "start": "2024-01-02 09:30:00",
            "end": "2024-01-02 15:00:00",
            "adjust": "",
            "path": "data/cache/minute/demo.parquet",
            "rows": 240,
            "source": "test",
            "status": "ok",
        }
    )

    catalog = store.market_catalog()

    assert catalog["universe"]["rows"] == 1
    assert catalog["daily_bars"]["rows"] == 1
    assert catalog["daily_bars"]["start"] == "2024-01-02"
    assert catalog["minute_bars"]["rows"] == 240


def test_sqlite_store_upsert_universe_normalizes_empty_text_fields(tmp_path):
    db_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(db_path)

    rows = store.upsert_universe(pd.DataFrame({"symbol": ["920000"], "name": ["安徽凤凰"], "market": ["BJ"], "board": ["BSE"], "industry": [pd.NA], "sector": [pd.NA]}))

    universe = store.read_universe()
    assert rows == 1
    assert universe.loc[0, "industry"] == ""
    assert universe.loc[0, "sector"] == ""


def test_import_batch_daily_uses_local_store_and_provider_chain(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "quant.sqlite"
    store = SQLiteStore(db_path)
    store.upsert_universe(pd.DataFrame({"symbol": ["000001", "000002"], "name": ["One", "Two"], "market": ["SZ", "SZ"], "board": ["MAIN", "MAIN"]}))

    def fake_fetch(symbol, start, end, adjust, source):
        frame = pd.DataFrame(
            {
                "symbol": [symbol],
                "date": ["2024-01-02"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.5],
                "close": [10.5],
                "volume": [1000],
            }
        )
        return ProviderResult(provider="fake", frame=frame)

    monkeypatch.setattr(cli, "_fetch_daily_without_health", fake_fetch)
    args = Namespace(
        db_path=db_path,
        universe=None,
        start="20240101",
        end="20240131",
        adjust="qfq",
        source="auto",
        limit=None,
        workers=2,
        progress_every=0,
        refresh=False,
        include_st=False,
        include_bj=False,
        settings=None,
    )

    cli.run_data_db_import_batch_daily(args)

    payload = capsys.readouterr().out
    assert '"ok": 2' in payload
    assert len(SQLiteStore(db_path).read_daily_bars()) == 2


def test_coverage_satisfies_non_trading_day_edges():
    item = {"start": "2021-01-04", "end": "2026-05-29"}

    assert cli._coverage_satisfies_request(item, "2021-01-01", "2026-05-30") is True


def test_coverage_satisfies_late_listing_dense_history():
    item = {"rows": 828, "start": "2022-12-12", "end": "2026-05-29"}

    assert cli._coverage_satisfies_request(item, "2021-01-01", "2026-05-30") is True
