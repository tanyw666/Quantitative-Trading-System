from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from quant_system.storage.jsonl import append_jsonl, read_jsonl
from quant_system.storage.sqlite_store import SQLiteStore


@dataclass(frozen=True)
class SelectionRecord:
    date: str
    strategy: str
    symbol: str
    name: str
    close: float
    reason: str
    entry_gate: str = ""
    dragon_state: str = ""
    dragon_tags: str = ""
    dragon_score: float = 0.0
    seal_quality_score: float = 0.0


class SelectionTracker:
    def __init__(self, path: Path, sqlite_path: Path | None = None) -> None:
        self.path = path
        self.sqlite_path = sqlite_path

    def record(self, selection: SelectionRecord) -> None:
        payload = asdict(selection)
        append_jsonl(self.path, payload)
        if self.sqlite_path is not None:
            store = SQLiteStore(self.sqlite_path)
            store.init()
            store.insert_selections([payload])

    def record_many(self, selections: list[SelectionRecord]) -> None:
        payloads = [asdict(selection) for selection in selections]
        for payload in payloads:
            append_jsonl(self.path, payload)
        if self.sqlite_path is not None and payloads:
            store = SQLiteStore(self.sqlite_path)
            store.init()
            store.insert_selections(payloads)

    def history(self) -> list[dict]:
        return read_jsonl(self.path)
