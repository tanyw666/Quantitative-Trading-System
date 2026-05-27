from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from quant_system.storage.jsonl import append_jsonl, read_jsonl


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
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, selection: SelectionRecord) -> None:
        append_jsonl(self.path, asdict(selection))

    def record_many(self, selections: list[SelectionRecord]) -> None:
        for selection in selections:
            self.record(selection)

    def history(self) -> list[dict]:
        return read_jsonl(self.path)
