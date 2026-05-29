from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from quant_system.storage.jsonl import append_jsonl, read_jsonl
from quant_system.storage.sqlite_store import SQLiteStore


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
    gate_status: str = ""
    gate_message: str = ""
    gate_reasons: list[str] = field(default_factory=list)
    workflow_summary: str = ""
    discipline_exception: bool = False
    exception_reason: str = ""

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
    def __init__(self, path: Path, sqlite_path: Path | None = None) -> None:
        self.path = path
        self.sqlite_path = sqlite_path

    def add(self, entry: TradeJournalEntry) -> None:
        payload = entry.to_record()
        append_jsonl(self.path, payload)
        if self.sqlite_path is not None:
            store = SQLiteStore(self.sqlite_path)
            store.init()
            store.insert_trade(payload)

    def list(self) -> list[dict]:
        return read_jsonl(self.path)


def summarize_trade_journal(records: list[dict]) -> dict:
    side_counts = Counter(str(record.get("side", "")).upper() for record in records)
    mistake_counts = Counter(record.get("mistake_type", "") for record in records if record.get("mistake_type"))
    gate_counts = Counter(str(record.get("gate_status", "") or "") for record in records if record.get("gate_status"))
    tag_counts: Counter[str] = Counter()
    total_amount = 0.0
    deviations = []
    gate_violation_count = 0
    discipline_exception_count = 0

    for record in records:
        total_amount += float(record.get("amount", 0.0) or 0.0)
        deviation = record.get("execution_deviation_pct")
        if deviation is not None:
            deviations.append(float(deviation))
        if str(record.get("side", "")).upper() == "BUY" and str(record.get("gate_status", "")) in {"warn", "block"}:
            gate_violation_count += 1
        if record.get("discipline_exception"):
            discipline_exception_count += 1
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
        "gate_counts": dict(gate_counts),
        "gate_violation_count": gate_violation_count,
        "discipline_exception_count": discipline_exception_count,
    }


def summarize_gate_journal(records: list[dict], limit: int = 20) -> dict:
    status_counts: Counter[str] = Counter()
    buy_status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    gate_records: list[dict] = []
    violations: list[dict] = []
    missing_gate_count = 0

    for record in records:
        status = str(record.get("gate_status", "") or "").strip().lower()
        if not status:
            missing_gate_count += 1
            continue
        side = str(record.get("side", "") or "").strip().upper()
        reasons = _normalise_reason_list(record.get("gate_reasons", []))
        item = {
            "date": str(record.get("date", "") or ""),
            "symbol": str(record.get("symbol", "") or ""),
            "name": str(record.get("name", "") or ""),
            "side": side,
            "strategy": str(record.get("strategy", "") or ""),
            "status": status,
            "message": str(record.get("gate_message", "") or ""),
            "reasons": reasons,
            "amount": float(record.get("amount", 0.0) or 0.0),
            "execution_deviation_pct": record.get("execution_deviation_pct"),
            "workflow_summary": str(record.get("workflow_summary", "") or ""),
        }
        gate_records.append(item)
        status_counts[status] += 1
        if side == "BUY":
            buy_status_counts[status] += 1
        if item["strategy"]:
            strategy_counts[item["strategy"]] += 1
        if item["symbol"]:
            symbol_counts[item["symbol"]] += 1
        reason_counts.update(reason for reason in reasons if reason)
        if side == "BUY" and status in {"warn", "block"}:
            violations.append(item)

    gate_buy_count = sum(buy_status_counts.values())
    violation_count = len(violations)
    visible_limit = max(int(limit), 0)
    visible_records = gate_records[-visible_limit:] if visible_limit else gate_records
    visible_violations = violations[-visible_limit:] if visible_limit else violations
    return {
        "total_trades": len(records),
        "gate_record_count": len(gate_records),
        "missing_gate_count": missing_gate_count,
        "status_counts": dict(status_counts),
        "buy_status_counts": dict(buy_status_counts),
        "gate_buy_count": gate_buy_count,
        "violation_count": violation_count,
        "violation_rate": violation_count / gate_buy_count if gate_buy_count else 0.0,
        "by_reason": dict(reason_counts),
        "by_strategy": dict(strategy_counts),
        "by_symbol": dict(symbol_counts),
        "latest_records": visible_records,
        "latest_violations": visible_violations,
        "action_items": _gate_action_items(
            missing_gate_count=missing_gate_count,
            violation_count=violation_count,
            reason_counts=reason_counts,
            status_counts=status_counts,
        ),
    }


def summarize_discipline_exceptions(records: list[dict], limit: int = 20) -> dict:
    exception_records: list[dict] = []
    missing_reason: list[dict] = []
    strategy_counts: Counter[str] = Counter()
    symbol_counts: Counter[str] = Counter()
    side_counts: Counter[str] = Counter()
    for record in records:
        if not record.get("discipline_exception"):
            continue
        item = {
            "date": str(record.get("date", "") or ""),
            "symbol": str(record.get("symbol", "") or ""),
            "name": str(record.get("name", "") or ""),
            "side": str(record.get("side", "") or "").upper(),
            "strategy": str(record.get("strategy", "") or ""),
            "amount": float(record.get("amount", 0.0) or 0.0),
            "gate_status": str(record.get("gate_status", "") or ""),
            "exception_reason": str(record.get("exception_reason", "") or "").strip(),
            "review": str(record.get("review", "") or ""),
        }
        exception_records.append(item)
        if item["strategy"]:
            strategy_counts[item["strategy"]] += 1
        if item["symbol"]:
            symbol_counts[item["symbol"]] += 1
        if item["side"]:
            side_counts[item["side"]] += 1
        if not item["exception_reason"]:
            missing_reason.append(item)

    visible_limit = max(int(limit), 0)
    visible_records = exception_records[-visible_limit:] if visible_limit else exception_records
    return {
        "total_trades": len(records),
        "exception_count": len(exception_records),
        "approved_exception_count": len(exception_records) - len(missing_reason),
        "missing_reason_count": len(missing_reason),
        "exception_rate": len(exception_records) / len(records) if records else 0.0,
        "by_strategy": dict(strategy_counts),
        "by_symbol": dict(symbol_counts),
        "by_side": dict(side_counts),
        "records": visible_records,
        "latest_missing_reason": missing_reason[-visible_limit:] if visible_limit else missing_reason,
        "action_items": _discipline_exception_action_items(
            exception_count=len(exception_records),
            missing_reason_count=len(missing_reason),
            strategy_counts=strategy_counts,
        ),
    }


def _normalise_reason_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _gate_action_items(
    *,
    missing_gate_count: int,
    violation_count: int,
    reason_counts: Counter[str],
    status_counts: Counter[str],
) -> list[str]:
    items: list[str] = []
    if missing_gate_count:
        items.append("Some trades have no gate snapshot; attach workflow summary or manual gate fields when recording trades.")
    if violation_count:
        items.append("Review every BUY executed under warn/block status and mark whether it was a planned exception.")
    if status_counts.get("block", 0):
        items.append("Blocked gate records should create next-day no-new-position discipline unless manually cleared.")
    if reason_counts:
        top_reason = _top_counter_key(reason_counts)
        items.append(f"Most common gate reason is '{top_reason}'; fix this upstream before increasing position size.")
    if not items:
        items.append("Gate discipline is clean in the current sample; keep recording every premarket gate before trading.")
    return items


def _top_counter_key(values: Counter[str]) -> str:
    items = [(str(key), int(value)) for key, value in values.items() if str(key)]
    if not items:
        return ""
    return sorted(items, key=lambda item: (-item[1], item[0]))[0][0]


def _discipline_exception_action_items(
    *,
    exception_count: int,
    missing_reason_count: int,
    strategy_counts: Counter[str],
) -> list[str]:
    items: list[str] = []
    if missing_reason_count:
        items.append("Every discipline exception must include an exception reason before it can be treated as approved.")
    if exception_count >= 3:
        items.append("Exception usage is becoming frequent; lower size or tighten entry rules until the count cools down.")
    if strategy_counts:
        strategy = _top_counter_key(strategy_counts)
        items.append(f"Most exceptions came from '{strategy}'; review whether this strategy needs a clearer playbook.")
    if not items:
        items.append("No discipline exceptions recorded; keep using explicit exception reasons only for planned overrides.")
    return items
