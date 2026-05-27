from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


REQUIRED_COLUMNS = ("date", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class DataHealthIssue:
    name: str
    status: str
    message: str

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
        issues.append(DataHealthIssue("required_columns", "fail", f"缺少必要字段：{', '.join(missing)}"))
        return DataHealthReport("fail", len(frame), 0, "", "", issues)

    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"])
    if "symbol" not in data.columns:
        data["symbol"] = "SINGLE"
    data["symbol"] = data["symbol"].astype(str).str.zfill(6)

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


def _check_duplicates(data: pd.DataFrame) -> DataHealthIssue:
    duplicates = int(data[["symbol", "date"]].duplicated().sum())
    if duplicates:
        return DataHealthIssue("duplicates", "fail", f"发现 {duplicates} 条 symbol+date 重复记录。")
    return DataHealthIssue("duplicates", "pass", "未发现重复记录。")


def _check_nulls(data: pd.DataFrame) -> DataHealthIssue:
    columns = list(REQUIRED_COLUMNS)
    null_count = int(data[columns].isna().sum().sum())
    if null_count:
        return DataHealthIssue("nulls", "fail", f"必要字段存在 {null_count} 个空值。")
    return DataHealthIssue("nulls", "pass", "必要字段无空值。")


def _check_price_sanity(data: pd.DataFrame) -> DataHealthIssue:
    bad = data[(data["high"] < data["low"]) | (data["close"] <= 0) | (data["open"] <= 0)]
    if not bad.empty:
        return DataHealthIssue("price_sanity", "fail", f"发现 {len(bad)} 条价格异常记录。")
    return DataHealthIssue("price_sanity", "pass", "价格字段基本合理。")


def _check_history_length(data: pd.DataFrame, min_rows_per_symbol: int) -> DataHealthIssue:
    counts = data.groupby("symbol")["date"].count()
    short = counts[counts < min_rows_per_symbol]
    if not short.empty:
        sample = ", ".join(short.index.astype(str).tolist()[:5])
        return DataHealthIssue(
            "history_length",
            "warn",
            f"{len(short)} 只股票历史长度小于 {min_rows_per_symbol}，示例：{sample}",
        )
    return DataHealthIssue("history_length", "pass", f"所有股票历史长度不少于 {min_rows_per_symbol}。")


def _check_staleness(data: pd.DataFrame, max_stale_days: int, as_of: str | pd.Timestamp | None) -> DataHealthIssue:
    as_of_date = pd.to_datetime(as_of) if as_of is not None else pd.Timestamp.today().normalize()
    latest = data["date"].max()
    stale_days = int((as_of_date.normalize() - latest.normalize()).days)
    if stale_days > max_stale_days:
        return DataHealthIssue("staleness", "warn", f"最新数据为 {latest:%Y-%m-%d}，已滞后 {stale_days} 天。")
    return DataHealthIssue("staleness", "pass", f"最新数据为 {latest:%Y-%m-%d}，滞后 {stale_days} 天。")


def _rollup(issues: list[DataHealthIssue]) -> str:
    statuses = {issue.status for issue in issues}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "ok"
