from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock

import json


@dataclass(frozen=True)
class ProviderHealthRecord:
    name: str
    success: int = 0
    failure: int = 0
    last_error: str = ""

    @property
    def score(self) -> float:
        total = self.success + self.failure
        if total <= 0:
            return 0.5
        return (self.success + 1.0) / (total + 2.0)


class ProviderHealthStore:
    _lock = RLock()

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, ProviderHealthRecord]:
        with self._lock:
            if not self.path.exists():
                return {}
            payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            records: dict[str, ProviderHealthRecord] = {}
            for name, item in payload.items():
                records[str(name)] = ProviderHealthRecord(
                    name=str(name),
                    success=int(item.get("success", 0)),
                    failure=int(item.get("failure", 0)),
                    last_error=str(item.get("last_error", "")),
                )
            return records

    def write(self, records: dict[str, ProviderHealthRecord]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {name: asdict(record) for name, record in records.items()}
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def update(self, name: str, ok: bool, error: str = "") -> None:
        with self._lock:
            records = self.read()
            current = records.get(name, ProviderHealthRecord(name=name))
            if ok:
                current = ProviderHealthRecord(name=name, success=current.success + 1, failure=current.failure, last_error="")
            else:
                current = ProviderHealthRecord(name=name, success=current.success, failure=current.failure + 1, last_error=error)
            records[name] = current
            payload = {record_name: asdict(record) for record_name, record in records.items()}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
