from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class DataHealthIssue:
    name: str
    status: str
    message: str
    details: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DataHealthReport:
    status: str
    rows: int
    symbols: int
    start_date: str
    end_date: str
    issues: list[DataHealthIssue]

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "rows": self.rows,
            "symbols": self.symbols,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def check_ohlcv_health(
    frame: pd.DataFrame,
    min_rows_per_symbol: int = 30,
    max_stale_days: int | None = None,
    as_of: str | pd.Timestamp | None = None,
) -> DataHealthReport:
    issues: list[DataHealthIssue] = []
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        issues.append(DataHealthIssue("required_columns", "fail", f"Missing required columns: {', '.join(missing)}"))
        return DataHealthReport("fail", len(frame), 0, "", "", issues)

    data = _prepare_health_frame(frame)

    issues.append(_check_duplicates(data))
    issues.append(_check_nulls(data))
    issues.append(_check_price_sanity(data))
    issues.append(_check_history_length(data, min_rows_per_symbol))
    if max_stale_days is not None:
        issues.append(_check_staleness(data, max_stale_days=max_stale_days, as_of=as_of))

    status = _rollup(issues)
    return DataHealthReport(
        status=status,
        rows=len(data),
        symbols=int(data["symbol"].nunique()),
        start_date=data["date"].min().strftime("%Y-%m-%d"),
        end_date=data["date"].max().strftime("%Y-%m-%d"),
        issues=issues,
    )


def build_ohlcv_repair_plan(
    frame: pd.DataFrame,
    min_rows_per_symbol: int = 30,
    max_stale_days: int = 10,
    as_of: str | pd.Timestamp | None = None,
) -> dict:
    data = _prepare_health_frame(frame)
    as_of_date = pd.to_datetime(as_of) if as_of is not None else pd.Timestamp.today().normalize()
    summary = _symbol_summary(data)
    summary["stale_days"] = (as_of_date.normalize() - summary["last"].dt.normalize()).dt.days
    summary["is_new_listing"] = _is_new_listing(summary, min_rows_per_symbol)
    summary["is_special_status"] = _is_special_status(summary)
    summary["short_history"] = summary["rows"] < min_rows_per_symbol
    summary["is_stale"] = summary["stale_days"] > max_stale_days

    recent_new = summary[summary["short_history"] & summary["is_new_listing"]].copy()
    backfill = summary[summary["short_history"] & ~summary["is_new_listing"] & ~summary["is_special_status"]].copy()
    regular_stale = summary[summary["is_stale"] & ~summary["is_special_status"]].copy()
    special_stale = summary[summary["is_stale"] & summary["is_special_status"]].copy()

    repair_targets = pd.concat([regular_stale, backfill], ignore_index=True, sort=False)
    priority_symbols = repair_targets["symbol"].drop_duplicates().astype(str).tolist()
    start_date = data["date"].min().strftime("%Y%m%d")
    end_date = as_of_date.strftime("%Y%m%d")

    return {
        "status": _repair_plan_status(priority_symbols, recent_new, special_stale),
        "as_of": f"{as_of_date:%Y-%m-%d}",
        "suggested_fetch_start": start_date,
        "suggested_fetch_end": end_date,
        "min_rows_per_symbol": min_rows_per_symbol,
        "max_stale_days": max_stale_days,
        "priority_symbols": priority_symbols,
        "refresh_candidates": _sample_records_with_limit(regular_stale.sort_values("stale_days", ascending=False), "stale_days", limit=None),
        "backfill_candidates": _sample_records_with_limit(backfill.sort_values("rows"), "rows", limit=None),
        "monitor_only": {
            "recent_new_listings": _sample_records_with_limit(recent_new.sort_values("rows"), "rows", limit=None),
            "special_status_stale": _sample_records_with_limit(special_stale.sort_values("stale_days", ascending=False), "stale_days", limit=None),
        },
        "recommended_steps": _recommended_steps(priority_symbols, recent_new, special_stale, start_date, end_date),
    }


def _check_duplicates(data: pd.DataFrame) -> DataHealthIssue:
    duplicates = int(data[["symbol", "date"]].duplicated().sum())
    if duplicates:
        return DataHealthIssue("duplicates", "fail", f"Found {duplicates} duplicate symbol+date rows.")
    return DataHealthIssue("duplicates", "pass", "No duplicate symbol+date rows found.")


def _check_nulls(data: pd.DataFrame) -> DataHealthIssue:
    columns = list(REQUIRED_COLUMNS)
    null_count = int(data[columns].isna().sum().sum())
    if null_count:
        return DataHealthIssue("nulls", "fail", f"Required OHLCV fields contain {null_count} null values.")
    return DataHealthIssue("nulls", "pass", "Required OHLCV fields have no null values.")


def _check_price_sanity(data: pd.DataFrame) -> DataHealthIssue:
    bad = data[
        (data["high"] < data["low"])
        | (data["close"] <= 0)
        | (data["open"] <= 0)
        | (data["high"] <= 0)
        | (data["low"] <= 0)
        | (data["volume"] < 0)
    ]
    if not bad.empty:
        return DataHealthIssue("price_sanity", "fail", f"Found {len(bad)} rows with invalid OHLCV values.")
    return DataHealthIssue("price_sanity", "pass", "OHLCV values pass basic sanity checks.")


def _check_history_length(data: pd.DataFrame, min_rows_per_symbol: int) -> DataHealthIssue:
    summary = _symbol_summary(data)
    short = summary[summary["rows"] < min_rows_per_symbol]
    if not short.empty:
        new_like = short[_is_new_listing(short, min_rows_per_symbol)]
        other = short.drop(index=new_like.index)
        parts: list[str] = []
        if not new_like.empty:
            parts.append(f"{len(new_like)} recent/new listings have short history: {_sample_rows(new_like, 'rows')}")
        if not other.empty:
            parts.append(f"{len(other)} symbols may need backfill: {_sample_rows(other, 'rows')}")
        return DataHealthIssue(
            "history_length",
            "warn",
            " | ".join(parts),
            {
                "min_rows_per_symbol": min_rows_per_symbol,
                "new_listing_count": int(len(new_like)),
                "new_listing_samples": _sample_records(new_like, "rows"),
                "backfill_count": int(len(other)),
                "backfill_samples": _sample_records(other, "rows"),
            },
        )
    return DataHealthIssue("history_length", "pass", f"All symbols have at least {min_rows_per_symbol} rows.")


def _check_staleness(data: pd.DataFrame, max_stale_days: int, as_of: str | pd.Timestamp | None) -> DataHealthIssue:
    as_of_date = pd.to_datetime(as_of) if as_of is not None else pd.Timestamp.today().normalize()
    summary = _symbol_summary(data)
    summary["stale_days"] = (as_of_date.normalize() - summary["last"].dt.normalize()).dt.days
    stale = summary[summary["stale_days"] > max_stale_days].sort_values("stale_days", ascending=False)
    if not stale.empty:
        special = stale[_is_special_status(stale)]
        normal = stale.drop(index=special.index)
        parts: list[str] = []
        if not normal.empty:
            parts.append(f"{len(normal)} regular symbols look stale: {_sample_rows(normal, 'stale_days', 'd')}")
        if not special.empty:
            parts.append(f"{len(special)} ST/special-status symbols stale separately: {_sample_rows(special, 'stale_days', 'd')}")
        latest = stale["last"].min().strftime("%Y-%m-%d")
        return DataHealthIssue(
            "staleness",
            "warn",
            f"{' | '.join(parts)}. As of {as_of_date:%Y-%m-%d}; oldest cached date reaches {latest}.",
            {
                "max_stale_days": max_stale_days,
                "as_of": f"{as_of_date:%Y-%m-%d}",
                "oldest_cached_date": latest,
                "regular_stale_count": int(len(normal)),
                "regular_stale_samples": _sample_records(normal, "stale_days"),
                "special_stale_count": int(len(special)),
                "special_stale_samples": _sample_records(special, "stale_days"),
            },
        )
    latest = summary["last"].max().strftime("%Y-%m-%d")
    return DataHealthIssue(
        "staleness",
        "pass",
        f"All symbols are within {max_stale_days} days of {as_of_date:%Y-%m-%d}. Latest cached date is {latest}.",
    )


def _symbol_summary(data: pd.DataFrame) -> pd.DataFrame:
    aggregations: dict[str, tuple[str, str]] = {
        "rows": ("date", "count"),
        "first": ("date", "min"),
        "last": ("date", "max"),
    }
    if "name" in data.columns:
        aggregations["name"] = ("name", "last")
    if "board" in data.columns:
        aggregations["board"] = ("board", "last")
    summary = data.groupby("symbol", as_index=False).agg(**aggregations)
    for column in ("name", "board"):
        if column not in summary.columns:
            summary[column] = ""
        summary[column] = summary[column].fillna("").astype(str)
    return summary


def _is_new_listing(summary: pd.DataFrame, min_rows_per_symbol: int) -> pd.Series:
    latest_date = summary["last"].max()
    active_recently = (latest_date.normalize() - summary["last"].dt.normalize()).dt.days <= 3
    short_span = (summary["last"].dt.normalize() - summary["first"].dt.normalize()).dt.days <= min_rows_per_symbol * 2
    return active_recently & short_span


def _is_special_status(summary: pd.DataFrame) -> pd.Series:
    name = summary.get("name", pd.Series([""] * len(summary), index=summary.index)).fillna("").astype(str).str.upper()
    return name.str.contains("ST", regex=False) | name.str.contains("退", regex=False)


def _sample_rows(summary: pd.DataFrame, value_column: str, suffix: str = "") -> str:
    parts: list[str] = []
    for row in summary.head(10).to_dict(orient="records"):
        name = str(row.get("name") or "").strip()
        label = f"{row.get('symbol', '')} {name}".strip()
        value = row.get(value_column, "")
        parts.append(f"{label}({int(value)}{suffix})")
    return ", ".join(parts)


def _sample_records(summary: pd.DataFrame, value_column: str) -> list[dict]:
    return _sample_records_with_limit(summary, value_column, limit=10)


def _sample_records_with_limit(summary: pd.DataFrame, value_column: str, limit: int | None = 10) -> list[dict]:
    records: list[dict] = []
    rows = summary if limit is None else summary.head(limit)
    for row in rows.to_dict(orient="records"):
        payload = {
            "symbol": str(row.get("symbol", "")),
            "name": str(row.get("name") or ""),
            value_column: int(row.get(value_column, 0) or 0),
        }
        if "first" in row:
            payload["first_date"] = pd.to_datetime(row["first"]).strftime("%Y-%m-%d")
        if "last" in row:
            payload["last_date"] = pd.to_datetime(row["last"]).strftime("%Y-%m-%d")
        records.append(payload)
    return records


def _prepare_health_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"])
    if "symbol" not in data.columns:
        data["symbol"] = "SINGLE"
    data["symbol"] = data["symbol"].astype(str).str.zfill(6)
    return data


def _repair_plan_status(priority_symbols: list[str], recent_new: pd.DataFrame, special_stale: pd.DataFrame) -> str:
    if priority_symbols:
        return "action_needed"
    if not recent_new.empty or not special_stale.empty:
        return "monitor_only"
    return "ok"


def _recommended_steps(
    priority_symbols: list[str],
    recent_new: pd.DataFrame,
    special_stale: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> list[str]:
    steps: list[str] = []
    if priority_symbols:
        joined = ",".join(priority_symbols[:20])
        steps.append(
            f"优先回填普通滞后/历史不足股票，共 {len(priority_symbols)} 只；建议按 symbol 分批执行，区间 {start_date} 到 {end_date}。首批: {joined}"
        )
    if not recent_new.empty:
        steps.append(f"近端新股 {len(recent_new)} 只，短历史属正常现象，先观察后续自然补齐。")
    if not special_stale.empty:
        steps.append(f"ST/特殊状态滞后 {len(special_stale)} 只，先核对是否停牌、风险警示或长期无交易。")
    if not steps:
        steps.append("当前无需额外回填，缓存健康状态良好。")
    return steps


def _rollup(issues: list[DataHealthIssue]) -> str:
    statuses = {issue.status for issue in issues}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "ok"
