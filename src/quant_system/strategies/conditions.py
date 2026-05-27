from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ConditionResult:
    passed: bool
    reason: str


def _series_value(row: pd.Series, name: str) -> Any:
    if name not in row.index:
        raise KeyError(f"Unknown field in condition: {name}")
    return row[name]


def _compare(left: Any, op: str, right: Any) -> bool:
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    if op == "eq":
        return left == right
    if op == "neq":
        return left != right
    raise ValueError(f"Unsupported comparison operator: {op}")


def evaluate_condition(row: pd.Series, condition: dict[str, Any]) -> ConditionResult:
    if "all" in condition:
        children = [evaluate_condition(row, child) for child in condition["all"]]
        passed = all(child.passed for child in children)
        joined = "; ".join(child.reason for child in children)
        return ConditionResult(passed, f"AND({joined})")

    if "any" in condition:
        children = [evaluate_condition(row, child) for child in condition["any"]]
        passed = any(child.passed for child in children)
        joined = "; ".join(child.reason for child in children)
        return ConditionResult(passed, f"OR({joined})")

    field = str(condition["field"])
    op = str(condition["op"])
    left = _series_value(row, field)

    if "field_right" in condition:
        right_name = str(condition["field_right"])
        right = _series_value(row, right_name)
        right_label = right_name
    else:
        right = condition["value"]
        right_label = repr(right)

    passed = _compare(left, op, right)
    return ConditionResult(passed, f"{field} {op} {right_label}: {left!r} vs {right!r}")
