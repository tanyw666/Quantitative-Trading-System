from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from quant_system.storage.jsonl import append_jsonl, read_jsonl


@dataclass(frozen=True)
class TradeJournalEntry:
    date: str
    symbol: str
    side: str
    price: float
    quantity: int
    reason: str
    name: str = ""
    strategy: str = ""
    market_regime: str = ""
    planned_pct: float = 0.0
    actual_pct: float = 0.0
    planned_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    tags: list[str] = field(default_factory=list)
    mistake_type: str = ""
    review: str = ""

    @property
    def amount(self) -> float:
        return self.price * self.quantity

    @property
    def execution_deviation_pct(self) -> float | None:
        if not self.planned_price:
            return None
        return self.price / self.planned_price - 1.0

    def to_record(self) -> dict:
        record = asdict(self)
        record["amount"] = self.amount
        record["execution_deviation_pct"] = self.execution_deviation_pct
        return record


class TradeJournal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def add(self, entry: TradeJournalEntry) -> None:
        append_jsonl(self.path, entry.to_record())

    def list(self) -> list[dict]:
        return read_jsonl(self.path)


def summarize_trade_journal(records: list[dict]) -> dict:
    side_counts = Counter(str(record.get("side", "")).upper() for record in records)
    mistake_counts = Counter(record.get("mistake_type", "") for record in records if record.get("mistake_type"))
    tag_counts: Counter[str] = Counter()
    total_amount = 0.0
    deviations = []

    for record in records:
        total_amount += float(record.get("amount", 0.0) or 0.0)
        deviation = record.get("execution_deviation_pct")
        if deviation is not None:
            deviations.append(float(deviation))
        tags = record.get("tags", [])
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.split(",") if item.strip()]
        tag_counts.update(tags)

    avg_deviation = sum(deviations) / len(deviations) if deviations else 0.0
    return {
        "total_trades": len(records),
        "buy_count": side_counts.get("BUY", 0),
        "sell_count": side_counts.get("SELL", 0),
        "total_amount": total_amount,
        "avg_execution_deviation_pct": avg_deviation,
        "mistake_counts": dict(mistake_counts),
        "tag_counts": dict(tag_counts),
    }
