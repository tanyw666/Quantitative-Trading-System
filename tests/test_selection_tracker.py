from pathlib import Path

from quant_system.portfolio.selection_tracker import SelectionRecord, SelectionTracker
from quant_system.storage.sqlite_store import SQLiteStore


def test_selection_tracker_can_dual_write_jsonl_and_sqlite(tmp_path: Path):
    tracker_path = tmp_path / "selections.jsonl"
    sqlite_path = tmp_path / "quant.sqlite"
    tracker = SelectionTracker(tracker_path, sqlite_path=sqlite_path)

    tracker.record(
        SelectionRecord(
            date="2026-05-29",
            strategy="dragon_leader",
            symbol="1",
            name="Demo",
            close=10.5,
            reason="测试入选",
            entry_gate="pass",
        )
    )

    history = tracker.history()
    stored = SQLiteStore(sqlite_path).read_selections(strategy="dragon_leader")

    assert history[0]["symbol"] == "1"
    assert stored.loc[0, "symbol"] == "000001"
    assert stored.loc[0, "entry_gate"] == "pass"
