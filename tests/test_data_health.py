import pandas as pd

from quant_system.data.health import build_ohlcv_repair_plan, check_ohlcv_health


def test_check_ohlcv_health_passes_clean_data():
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=30),
            "symbol": ["000001"] * 30,
            "open": [10] * 30,
            "high": [11] * 30,
            "low": [9] * 30,
            "close": [10] * 30,
            "volume": [1000] * 30,
        }
    )

    report = check_ohlcv_health(frame, min_rows_per_symbol=30)

    assert report.status == "ok"
    assert report.symbols == 1


def test_check_ohlcv_health_fails_duplicate_dates():
    frame = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01"],
            "symbol": ["000001", "000001"],
            "open": [10, 10],
            "high": [11, 11],
            "low": [9, 9],
            "close": [10, 10],
            "volume": [1000, 1000],
        }
    )

    report = check_ohlcv_health(frame, min_rows_per_symbol=1)

    assert report.status == "fail"
    assert any(issue.name == "duplicates" for issue in report.issues)


def test_check_ohlcv_health_warns_on_symbol_level_staleness():
    frame = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-10"],
            "symbol": ["000001", "000002"],
            "open": [10, 10],
            "high": [11, 11],
            "low": [9, 9],
            "close": [10, 10],
            "volume": [1000, 1000],
        }
    )

    report = check_ohlcv_health(frame, min_rows_per_symbol=1, max_stale_days=3, as_of="2024-01-10")

    assert report.status == "warn"
    assert any(issue.name == "staleness" and "000001" in issue.message for issue in report.issues)


def test_check_ohlcv_health_classifies_new_listings_as_short_history_context():
    new_listing = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-05-27", "2026-05-28"]),
            "symbol": ["001001", "001001"],
            "name": ["新股样例", "新股样例"],
            "open": [10, 10],
            "high": [11, 11],
            "low": [9, 9],
            "close": [10, 10],
            "volume": [1000, 1000],
        }
    )
    old_stock = pd.DataFrame(
        {
            "date": pd.date_range("2026-04-01", periods=30),
            "symbol": ["000001"] * 30,
            "name": ["老股样例"] * 30,
            "open": [10] * 30,
            "high": [11] * 30,
            "low": [9] * 30,
            "close": [10] * 30,
            "volume": [1000] * 30,
        }
    )
    frame = pd.concat([new_listing, old_stock], ignore_index=True)

    report = check_ohlcv_health(frame, min_rows_per_symbol=30)
    issue = next(issue for issue in report.issues if issue.name == "history_length")
    message = issue.message

    assert "recent/new listings" in message
    assert "001001 新股样例" in message
    assert issue.details is not None
    assert issue.details["new_listing_count"] == 1
    assert issue.details["backfill_count"] == 0
    assert issue.details["new_listing_samples"][0]["symbol"] == "001001"


def test_check_ohlcv_health_separates_special_status_staleness():
    frame = pd.DataFrame(
        {
            "date": ["2026-04-20", "2026-04-21"],
            "symbol": ["000004", "000005"],
            "name": ["*ST国华", "普通股票"],
            "open": [10, 10],
            "high": [11, 11],
            "low": [9, 9],
            "close": [10, 10],
            "volume": [1000, 1000],
        }
    )

    report = check_ohlcv_health(frame, min_rows_per_symbol=1, max_stale_days=10, as_of="2026-05-29")
    issue = next(issue for issue in report.issues if issue.name == "staleness")
    message = issue.message

    assert "regular symbols look stale" in message
    assert "ST/special-status symbols stale separately" in message
    assert "000004 *ST国华" in message
    assert "000005 普通股票" in message
    assert issue.details is not None
    assert issue.details["regular_stale_count"] == 1
    assert issue.details["special_stale_count"] == 1
    assert issue.details["regular_stale_samples"][0]["symbol"] == "000005"


def test_build_ohlcv_repair_plan_prioritizes_regular_stale_and_monitors_context():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-05-28", "2026-04-20", "2026-04-20", "2026-05-28", "2026-05-27"]),
            "symbol": ["000001", "688121", "000004", "001001", "001001"],
            "name": ["正常股票", "卓然股份", "*ST国华", "新股样例", "新股样例"],
            "open": [10, 10, 10, 10, 10],
            "high": [11, 11, 11, 11, 11],
            "low": [9, 9, 9, 9, 9],
            "close": [10, 10, 10, 10, 10],
            "volume": [1000, 1000, 1000, 1000, 1000],
        }
    )

    plan = build_ohlcv_repair_plan(frame, min_rows_per_symbol=2, max_stale_days=10, as_of="2026-05-29")

    assert plan["status"] == "action_needed"
    assert plan["priority_symbols"] == ["688121"]
    assert plan["refresh_candidates"][0]["symbol"] == "688121"
    assert plan["monitor_only"]["special_status_stale"][0]["symbol"] == "000004"
    assert any("优先回填" in step for step in plan["recommended_steps"])
