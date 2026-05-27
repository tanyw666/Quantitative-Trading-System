from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from quant_system.storage.jsonl import append_jsonl


@dataclass(frozen=True)
class DecisionEvent:
    date: str
    symbol: str
    stage: str
    action: str
    passed: bool
    reason: str
    details: dict[str, Any]

    @classmethod
    def from_timestamp(
        cls,
        date: pd.Timestamp,
        symbol: str,
        stage: str,
        action: str,
        passed: bool,
        reason: str,
        details: dict[str, Any] | None = None,
    ) -> "DecisionEvent":
        return cls(
            date=date.strftime("%Y-%m-%d"),
            symbol=symbol,
            stage=stage,
            action=action,
            passed=passed,
            reason=reason,
            details=details or {},
        )


class DecisionRecorder:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.events: list[DecisionEvent] = []

    def record(self, event: DecisionEvent) -> None:
        self.events.append(event)
        if self.path:
            append_jsonl(self.path, asdict(event))
