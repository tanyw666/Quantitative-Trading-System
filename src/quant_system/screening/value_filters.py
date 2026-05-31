from __future__ import annotations

from typing import Any

import pandas as pd


def add_value_filter_fields(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if data.empty:
        return data

    st_flags = _truthy_series(data, "st_flag") | _truthy_series(data, "is_st")
    if "name" in data.columns:
        names = data["name"].fillna("").astype(str)
        st_flags = st_flags | names.str.upper().str.contains("ST", regex=False) | names.str.contains("退", regex=False) | names.str.contains("閫€", regex=False)

    delisting_flags = _truthy_series(data, "delisting_risk_flag") | _truthy_series(data, "delisting_flag")
    pe_warnings = _non_positive_series(data["pe_ttm"] if "pe_ttm" in data.columns else data.get("pe"), data.index)
    pb_warnings = _non_positive_series(data["pb"] if "pb" in data.columns else data.get("pb_mrq"), data.index)
    market_cap_missing = _market_cap_missing_series(data)

    data["st_flag"] = st_flags
    data["delisting_risk_flag"] = delisting_flags
    data["value_warning_count"] = [
        int(pe_warning) + int(pb_warning) + int(market_cap_warning)
        for pe_warning, pb_warning, market_cap_warning in zip(pe_warnings, pb_warnings, market_cap_missing)
    ]
    data["value_landmine_flag"] = [
        bool(st_flag or delisting_flag)
        for st_flag, delisting_flag in zip(st_flags, delisting_flags)
    ]
    data["value_filter_status"] = [
        "block" if landmine else "warn" if warning_count else "pass"
        for landmine, warning_count in zip(data["value_landmine_flag"], data["value_warning_count"])
    ]
    data["value_filter_reason"] = [
        _reason(st_flag, delisting_flag, pe_warning, pb_warning, cap_warning)
        for st_flag, delisting_flag, pe_warning, pb_warning, cap_warning in zip(
            st_flags,
            delisting_flags,
            pe_warnings,
            pb_warnings,
            market_cap_missing,
        )
    ]
    return data


def _truthy_series(data: pd.DataFrame, column: str) -> pd.Series:
    if column not in data.columns:
        return pd.Series(False, index=data.index)
    values = data[column]
    if pd.api.types.is_string_dtype(values):
        return values.fillna("").astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y", "on", "st"})
    return values.fillna(False).astype(bool)


def _non_positive_series(values: pd.Series | None, index: pd.Index) -> pd.Series:
    if values is None:
        return pd.Series(False, index=index)
    non_empty = values.notna() & (values.astype(str).str.strip() != "")
    numeric = pd.to_numeric(values, errors="coerce")
    return non_empty & numeric.le(0)


def _market_cap_missing_series(data: pd.DataFrame) -> pd.Series:
    has_any_market_cap_column = any(column in data.columns for column in ("market_cap", "total_market_cap", "circulating_market_cap"))
    if not has_any_market_cap_column:
        return pd.Series(False, index=data.index)

    has_value = pd.Series(False, index=data.index)
    for column in ("market_cap", "total_market_cap", "circulating_market_cap"):
        if column not in data.columns:
            continue
        values = data[column]
        has_value = has_value | (values.notna() & (values.astype(str).str.strip() != ""))
    return (~_truthy_series(data, "microcap_strategy")) & (~has_value)


def _st_flag(row: dict[str, Any]) -> bool:
    if _truthy(row.get("st_flag")) or _truthy(row.get("is_st")):
        return True
    name = str(row.get("name", "") or "").upper()
    return "ST" in name or "退" in str(row.get("name", "") or "")


def _non_positive(value: Any) -> bool:
    if value in (None, ""):
        return False
    try:
        return float(value) <= 0
    except (TypeError, ValueError):
        return False


def _market_cap_missing(row: dict[str, Any]) -> bool:
    if _truthy(row.get("microcap_strategy")):
        return False
    for key in ("market_cap", "total_market_cap", "circulating_market_cap"):
        value = row.get(key)
        if value not in (None, ""):
            return False
    return any(key in row for key in ("market_cap", "total_market_cap", "circulating_market_cap"))


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "st"}
    return bool(value)


def _reason(
    st_flag: bool,
    delisting_flag: bool,
    pe_warning: bool,
    pb_warning: bool,
    cap_warning: bool,
) -> str:
    reasons: list[str] = []
    if st_flag:
        reasons.append("ST risk")
    if delisting_flag:
        reasons.append("delisting risk")
    if pe_warning:
        reasons.append("non-positive PE")
    if pb_warning:
        reasons.append("non-positive PB")
    if cap_warning:
        reasons.append("missing market cap")
    return "; ".join(reasons)
