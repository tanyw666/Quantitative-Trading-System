from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class Signal:
    date: pd.Timestamp
    symbol: str
    action: str
    price: float
    reason: str


class Strategy(Protocol):
    name: str

    def generate_signals(self, frame: pd.DataFrame) -> pd.DataFrame:
        ...

    def screen(self, frame: pd.DataFrame) -> pd.DataFrame:
        ...
