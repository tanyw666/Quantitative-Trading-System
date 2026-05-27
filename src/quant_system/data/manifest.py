from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from quant_system.storage.jsonl import append_jsonl, read_jsonl


@dataclass(frozen=True)
class CacheManifestEntry:
    symbol: str
    provider: str
    path: str
    start: str
    end: str
    rows: int
    status: str
    error: str = ""


class CacheManifest:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, entry: CacheManifestEntry) -> None:
        append_jsonl(self.path, asdict(entry))

    def read(self) -> list[dict]:
        return read_jsonl(self.path)
