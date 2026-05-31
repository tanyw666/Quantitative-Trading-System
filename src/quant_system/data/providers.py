from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import re
from pathlib import Path
from time import sleep
from typing import Any, Protocol
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from quant_system.data.provider_health import ProviderHealthRecord, ProviderHealthStore


class DailyBarProvider(Protocol):
    name: str

    def fetch_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        ...


class TableProvider(Protocol):
    name: str

    def fetch(self, **kwargs: Any) -> pd.DataFrame:
        ...


class MinuteBarProvider(Protocol):
    name: str

    def fetch_minute(self, symbol: str, start: str, end: str, period: str = "1", adjust: str = "") -> pd.DataFrame:
        ...


class AdjustmentFactorProvider(Protocol):
    name: str

    def fetch_adjustment_factors(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        ...


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    frame: pd.DataFrame
    attempts: list[dict[str, str]] = field(default_factory=list)


def normalize_daily_bars(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    rename_map = {
        "\u65e5\u671f": "date",
        "\u65f6\u95f4": "date",
        "\u65e5\u671f\u65f6\u95f4": "date",
        "datetime": "date",
        "trade_date": "date",
        "open": "open",
        "\u5f00\u76d8": "open",
        "open_price": "open",
        "close": "close",
        "\u6536\u76d8": "close",
        "close_price": "close",
        "high": "high",
        "\u6700\u9ad8": "high",
        "high_price": "high",
        "low": "low",
        "\u6700\u4f4e": "low",
        "low_price": "low",
        "volume": "volume",
        "\u6210\u4ea4\u91cf": "volume",
        "vol": "volume",
        "amount": "amount",
        "\u6210\u4ea4\u989d": "amount",
        "turnover": "turnover",
        "\u6362\u624b\u7387": "turnover",
        "turnover_value": "amount",
        "\u6da8\u8dcc\u5e45": "pct_change",
        "pct_change": "pct_change",
        "change_pct": "pct_change",
    }
    data = frame.rename(columns=rename_map).copy()
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Provider returned missing columns: {missing}")

    data["symbol"] = str(symbol).zfill(6)
    data["date"] = pd.to_datetime(data["date"], errors="raise")
    for column in ["open", "high", "low", "close", "volume"]:
        data[column] = pd.to_numeric(data[column], errors="raise")
    if "amount" in data.columns:
        data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
    if "turnover" in data.columns:
        data["turnover"] = pd.to_numeric(data["turnover"], errors="coerce")
    if "turnover_rate" not in data.columns and "turnover" in data.columns:
        data["turnover_rate"] = data["turnover"]
    if "pct_change" in data.columns:
        data["pct_change"] = pd.to_numeric(data["pct_change"], errors="coerce")
    data = _drop_daily_placeholder_rows(data)
    data = data.sort_values("date").reset_index(drop=True)
    if "pre_close" not in data.columns:
        data["pre_close"] = data["close"].shift(1)
    _validate_daily_frame(data, symbol)
    return data


def normalize_minute_bars(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    rename_map = {
        "\u65f6\u95f4": "datetime",
        "\u65e5\u671f\u65f6\u95f4": "datetime",
        "date": "datetime",
        "time": "datetime",
        "datetime": "datetime",
        "open": "open",
        "\u5f00\u76d8": "open",
        "close": "close",
        "\u6536\u76d8": "close",
        "high": "high",
        "\u6700\u9ad8": "high",
        "low": "low",
        "\u6700\u4f4e": "low",
        "volume": "volume",
        "\u6210\u4ea4\u91cf": "volume",
        "amount": "amount",
        "\u6210\u4ea4\u989d": "amount",
        "turnover": "turnover",
        "\u6362\u624b\u7387": "turnover",
    }
    data = frame.rename(columns=rename_map).copy()
    required = ["datetime", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"Provider returned missing minute columns: {missing}")
    data["symbol"] = str(symbol).zfill(6)
    data["datetime"] = pd.to_datetime(data["datetime"], errors="raise")
    for column in ["open", "high", "low", "close", "volume"]:
        data[column] = pd.to_numeric(data[column], errors="raise")
    if "amount" in data.columns:
        data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
    if "turnover" in data.columns:
        data["turnover"] = pd.to_numeric(data["turnover"], errors="coerce")
    data = data.sort_values("datetime").reset_index(drop=True)
    _validate_minute_frame(data, symbol)
    columns = [column for column in ("symbol", "datetime", "open", "high", "low", "close", "volume", "amount", "turnover") if column in data.columns]
    return data[columns]


def normalize_adjustment_factors(frame: pd.DataFrame, symbol: str, adjust: str = "qfq") -> pd.DataFrame:
    factor_column = f"{adjust or 'qfq'}_factor"
    rename_map = {
        "date": "date",
        "\u65e5\u671f": "date",
        factor_column: "adjust_factor",
        "factor": "adjust_factor",
        "adjust_factor": "adjust_factor",
    }
    data = frame.rename(columns=rename_map).copy()
    missing = [column for column in ("date", "adjust_factor") if column not in data.columns]
    if missing:
        raise ValueError(f"Provider returned missing adjustment factor columns: {missing}")
    data["symbol"] = str(symbol).zfill(6)
    data["date"] = pd.to_datetime(data["date"], errors="raise")
    data["adjust_factor"] = pd.to_numeric(data["adjust_factor"], errors="raise")
    data = data.sort_values("date").reset_index(drop=True)
    if (data["adjust_factor"] <= 0).any():
        raise ValueError("Provider returned non-positive adjustment factors")
    return data[["symbol", "date", "adjust_factor"]]


def _http_get_text(url: str, timeout: float = 10.0) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = item.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _parse_chain(source: str) -> list[str]:
    normalized = (source or "auto").strip().lower()
    if not normalized or normalized == "auto":
        return ["sina", "tencent", "akshare", "mootdx"]
    if re.search(r"[>,|/]+", normalized):
        return _dedupe_preserve_order(re.split(r"[>,|/]+", normalized))
    if normalized in {"mootdx", "tencent", "akshare", "sina"}:
        if normalized == "mootdx":
            return ["mootdx", "tencent", "akshare", "sina"]
        if normalized == "tencent":
            return ["tencent", "akshare", "sina"]
        if normalized == "akshare":
            return ["akshare", "sina"]
        return ["sina"]
    raise ValueError(f"Unknown data source: {source}")


def _fetch_akshare(method_name: str, **kwargs: Any) -> pd.DataFrame:
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise RuntimeError("AkShare is not installed. Run: python -m pip install -e .[data]") from exc
    method = getattr(ak, method_name)
    return method(**kwargs)


def _fetch_akshare_daily(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    raw = _fetch_akshare("stock_zh_a_hist", symbol=symbol, period="daily", start_date=start, end_date=end, adjust=adjust)
    return normalize_daily_bars(raw, symbol)


def _fetch_akshare_minute(symbol: str, start: str, end: str, period: str, adjust: str) -> pd.DataFrame:
    raw = _fetch_akshare("stock_zh_a_hist_min_em", symbol=symbol, start_date=start, end_date=end, period=period, adjust=adjust)
    return normalize_minute_bars(raw, symbol)


def _fetch_tencent_minute(symbol: str, start: str, end: str, period: str, adjust: str) -> pd.DataFrame:
    if adjust:
        raise RuntimeError("Tencent minute endpoint only supports raw minute bars")
    code = f"{_market_prefix(symbol)}{str(symbol).zfill(6)}"
    period_key = f"m{period}"
    url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?{urlencode({'param': f'{code},{period_key},,320'})}"
    try:
        payload = json.loads(_http_get_text(url))
    except (json.JSONDecodeError, URLError) as exc:
        raise RuntimeError(f"Tencent minute endpoint failed for {symbol}") from exc
    rows = (((payload.get("data") or {}).get(code) or {}).get(period_key) or []) if isinstance(payload, dict) else []
    parsed_rows: list[dict[str, object]] = []
    for row in rows:
        values = list(row) if isinstance(row, (list, tuple)) else []
        if len(values) < 6:
            continue
        parsed_rows.append(
            {
                "datetime": values[0],
                "open": values[1],
                "close": values[2],
                "high": values[3],
                "low": values[4],
                "volume": values[5],
            }
        )
    if not parsed_rows:
        raise RuntimeError(f"Tencent minute endpoint returned no rows for {symbol}")
    frame = pd.DataFrame(parsed_rows)
    frame["datetime"] = pd.to_datetime(frame["datetime"], format="%Y%m%d%H%M", errors="coerce")
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    frame = frame[(frame["datetime"] >= start_dt) & (frame["datetime"] <= end_dt)].reset_index(drop=True)
    if frame.empty:
        raise RuntimeError(f"Tencent minute endpoint has no rows in requested range for {symbol}")
    return normalize_minute_bars(frame, symbol)


def _fetch_akshare_adjustment_factors(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    mode = "hfq" if adjust == "hfq" else "qfq"
    raw = _fetch_akshare(
        "stock_zh_a_daily",
        symbol=f"{_market_prefix(symbol)}{str(symbol).zfill(6)}",
        start_date=start,
        end_date=end,
        adjust=f"{mode}-factor",
    )
    frame = normalize_adjustment_factors(raw, symbol, mode)
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    return frame[(frame["date"] >= start_dt) & (frame["date"] <= end_dt)].reset_index(drop=True)


def _fetch_sina_daily(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    if str(symbol).zfill(6).startswith("689"):
        raw = _fetch_akshare("stock_zh_a_cdr_daily", symbol=f"sh{str(symbol).zfill(6)}", start_date=start, end_date=end)
        return normalize_daily_bars(raw, symbol)
    prefix = _market_prefix(symbol)
    raw = _fetch_akshare("stock_zh_a_daily", symbol=f"{prefix}{symbol}", start_date=start, end_date=end, adjust=adjust)
    return normalize_daily_bars(raw, symbol)


def _fetch_tencent_daily(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    code = f"{_market_prefix(symbol)}{str(symbol).zfill(6)}"
    adjust_key = {"": "day", "qfq": "qfqday", "hfq": "hfqday"}.get(adjust, "qfqday")
    url = f"https://web.ifzq.gtimg.cn/appstock/app/day/query?{urlencode({'code': code})}"

    try:
        payload = json.loads(_http_get_text(url))
    except (json.JSONDecodeError, URLError) as exc:
        raise RuntimeError(f"Tencent daily endpoint failed for {symbol}") from exc

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    block = data.get(code) or next(iter(data.values()), {})
    rows = block.get(adjust_key) or block.get("day") or block.get("qfqday") or block.get("hfqday")
    if not rows:
        raise RuntimeError(f"Tencent daily endpoint returned no rows for {symbol}")

    parsed_rows: list[dict[str, object]] = []
    for row in rows:
        values = list(row) if isinstance(row, (list, tuple)) else []
        if len(values) < 6:
            continue
        parsed_rows.append(
            {
                "date": values[0],
                "open": values[1],
                "high": values[2],
                "low": values[3],
                "close": values[4],
                "volume": values[5],
                "amount": values[6] if len(values) > 6 else None,
                "turnover": values[8] if len(values) > 8 else None,
            }
        )
    if not parsed_rows:
        raise RuntimeError(f"Tencent daily endpoint returned unusable rows for {symbol}")

    frame = pd.DataFrame(parsed_rows)
    frame = frame[(pd.to_datetime(frame["date"]) >= pd.to_datetime(start)) & (pd.to_datetime(frame["date"]) <= pd.to_datetime(end))]
    return normalize_daily_bars(frame, symbol)


def _market_prefix(symbol: str) -> str:
    code = str(symbol).zfill(6)
    if code.startswith(("4", "8", "9")) and not code.startswith(("600", "601", "603", "605", "688", "689")):
        return "bj"
    if code.startswith(("6", "9")):
        return "sh"
    return "sz"


def _recent_notice_dates(value: Any, lookback_days: int = 7) -> list[str]:
    text = str(value or datetime.today().strftime("%Y%m%d")).strip().replace("-", "")
    try:
        current = datetime.strptime(text[:8], "%Y%m%d")
    except ValueError:
        current = datetime.today()
    days = max(1, lookback_days)
    return [(current - timedelta(days=offset)).strftime("%Y%m%d") for offset in range(days)]


def _fetch_mootdx_daily(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    try:
        from mootdx.quotes import Quotes  # type: ignore
        from mootdx.reader import Reader  # type: ignore
    except ImportError as exc:
        raise RuntimeError("mootdx is not installed. Install it before using the mootdx source.") from exc

    errors: list[str] = []
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    tdxdir = Path.home() / "tdx"

    try:
        reader_kwargs: dict[str, object] = {"market": "std"}
        if tdxdir.exists():
            reader_kwargs["tdxdir"] = str(tdxdir)
        reader = Reader.factory(**reader_kwargs)
        raw = reader.daily(symbol=symbol)
        frame = normalize_daily_bars(pd.DataFrame(raw), symbol)
        frame = frame[(frame["date"] >= start_dt) & (frame["date"] <= end_dt)].reset_index(drop=True)
        if not frame.empty:
            return frame
        errors.append("Reader.daily returned no rows")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Reader.factory/daily: {exc}")

    try:
        client = Quotes.factory(market="std", multithread=True, heartbeat=True)
        offset = max(120, int((end_dt - start_dt).days * 3) + 20)
        for frequency in (9, "day", "days"):
            try:
                raw = client.bars(symbol=symbol, frequency=frequency, offset=offset)
            except TypeError:
                raw = client.bars(symbol=symbol, market="std", frequency=frequency, offset=offset)
            frame = normalize_daily_bars(pd.DataFrame(raw), symbol)
            frame = frame[(frame["date"] >= start_dt) & (frame["date"] <= end_dt)].reset_index(drop=True)
            if not frame.empty:
                return frame
        errors.append("Quotes.bars returned no rows")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Quotes.factory/bars: {exc}")

    raise RuntimeError("mootdx provider could not load daily bars. " f"Details: {' | '.join(errors)}")


def _fetch_akshare_table(method_name: str, **kwargs: Any) -> pd.DataFrame:
    try:
        return _fetch_akshare(method_name, **kwargs)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"AkShare method {method_name} failed: {exc}") from exc


class AkShareDailyProvider:
    name = "akshare"

    def fetch_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        return _fetch_akshare_daily(symbol, start, end, adjust)


class AkShareMinuteProvider:
    name = "akshare-minute"

    def fetch_minute(self, symbol: str, start: str, end: str, period: str = "1", adjust: str = "") -> pd.DataFrame:
        return _fetch_akshare_minute(symbol, start, end, period, adjust)


class TencentMinuteProvider:
    name = "tencent-minute"

    def fetch_minute(self, symbol: str, start: str, end: str, period: str = "1", adjust: str = "") -> pd.DataFrame:
        return _fetch_tencent_minute(symbol, start, end, period, adjust)


class AkShareAdjustmentFactorProvider:
    name = "akshare-adjustment"

    def fetch_adjustment_factors(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        return _fetch_akshare_adjustment_factors(symbol, start, end, adjust)


class SinaDailyProvider:
    name = "sina"

    def fetch_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        return _fetch_sina_daily(symbol, start, end, adjust)


class TencentDailyProvider:
    name = "tencent"

    def fetch_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        return _fetch_tencent_daily(symbol, start, end, adjust)


class MootdxDailyProvider:
    name = "mootdx"

    def fetch_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
        return _fetch_mootdx_daily(symbol, start, end, adjust)


class AkShareConceptProvider:
    name = "akshare-concept"

    def fetch(self, **kwargs: Any) -> pd.DataFrame:
        errors: list[str] = []
        for method_name in ("stock_board_concept_name_em", "stock_board_concept_summary_ths", "stock_board_concept_name_ths"):
            try:
                return _fetch_akshare_table(method_name, **kwargs)
            except Exception as exc:  # noqa: BLE001 - concept providers are unstable; keep fallback local.
                errors.append(f"{method_name}: {exc}")
        raise RuntimeError("Concept providers failed: " + " | ".join(errors))


class AkShareAnnouncementProvider:
    name = "akshare-announcement"

    def fetch(self, **kwargs: Any) -> pd.DataFrame:
        errors: list[str] = []
        symbol = kwargs.get("symbol", "全部")
        security = str(kwargs.get("security") or "").strip()
        if security and security != "全部":
            return _fetch_akshare_table(
                "stock_individual_notice_report",
                security=security,
                symbol=symbol,
                begin_date=kwargs.get("begin_date") or kwargs.get("date"),
                end_date=kwargs.get("end_date") or kwargs.get("date"),
            )

        for notice_date in _recent_notice_dates(kwargs.get("date"), lookback_days=int(kwargs.get("lookback_days", 7))):
            try:
                frame = _fetch_akshare_table("stock_notice_report", symbol=symbol, date=notice_date)
                if not frame.empty:
                    return frame
                errors.append(f"stock_notice_report {notice_date}: empty result")
            except Exception as exc:  # noqa: BLE001 - announcement endpoint can be date-sensitive.
                errors.append(f"stock_notice_report {notice_date}: {exc}")
        raise RuntimeError("Announcement providers failed: " + " | ".join(errors))


class AkShareNewsProvider:
    name = "akshare-news"

    def fetch(self, **kwargs: Any) -> pd.DataFrame:
        errors: list[str] = []
        candidates = [
            ("stock_news_em", kwargs),
            ("stock_info_global_em", {}),
            ("stock_info_global_sina", {}),
            ("stock_news_main_cx", {}),
            ("stock_info_global_cls", {"symbol": kwargs.get("symbol", "全部")}),
        ]
        for method_name, method_kwargs in candidates:
            try:
                return _fetch_akshare_table(method_name, **method_kwargs)
            except Exception as exc:  # noqa: BLE001 - news providers are unstable; keep fallback local.
                errors.append(f"{method_name}: {exc}")
        raise RuntimeError("News providers failed: " + " | ".join(errors))


class SinaGlobalProvider:
    name = "sina-global"

    def fetch(self, **kwargs: Any) -> pd.DataFrame:
        market = kwargs.get("market", "global")
        if market == "global":
            try:
                return _fetch_akshare_table("stock_zh_index_spot_sina")
            except Exception as exc:
                raise RuntimeError(f"Sina global market fetch failed: {exc}") from exc
        raise ValueError(f"Unsupported market: {market}")


class WencaiUniverseProvider:
    name = "iwencai"

    def fetch(self, **kwargs: Any) -> pd.DataFrame:
        query = str(kwargs.get("query", "")).strip()
        if not query:
            raise ValueError("query is required")
        try:
            return _fetch_akshare_table("stock_query_wencai", query=query)
        except Exception as exc:
            raise RuntimeError(f"iWenCai query failed: {exc}") from exc


def provider_chain(source: str = "auto") -> list[DailyBarProvider]:
    providers = {
        "mootdx": MootdxDailyProvider(),
        "tencent": TencentDailyProvider(),
        "akshare": AkShareDailyProvider(),
        "sina": SinaDailyProvider(),
    }
    return [providers[name] for name in _parse_chain(source)]


def minute_provider_chain(source: str = "auto") -> list[MinuteBarProvider]:
    providers = {
        "akshare-minute": AkShareMinuteProvider(),
        "tencent-minute": TencentMinuteProvider(),
    }
    normalized = (source or "auto").strip().lower()
    if normalized in {"auto", ""}:
        return [providers["akshare-minute"], providers["tencent-minute"]]
    if normalized in {"akshare", "akshare-minute"}:
        return [providers["akshare-minute"], providers["tencent-minute"]]
    if normalized in {"tencent", "tencent-minute"}:
        return [providers["tencent-minute"]]
    raise ValueError(f"Unknown minute data source: {source}")


def ordered_provider_chain(source: str = "auto", health_path: Path | None = None) -> list[DailyBarProvider]:
    chain = provider_chain(source)
    if health_path is None:
        return chain
    store = ProviderHealthStore(health_path)
    health = store.read()
    return sorted(chain, key=lambda provider: health.get(provider.name, ProviderHealthRecord(name=provider.name)).score, reverse=True)


def table_provider_chain(source: str = "auto") -> list[TableProvider]:
    providers = {
        "akshare-concept": AkShareConceptProvider(),
        "akshare-announcement": AkShareAnnouncementProvider(),
        "akshare-news": AkShareNewsProvider(),
        "sina-global": SinaGlobalProvider(),
        "iwencai": WencaiUniverseProvider(),
    }
    if source.strip().lower() in {"auto", ""}:
        return [
            providers["akshare-concept"],
            providers["akshare-announcement"],
            providers["akshare-news"],
            providers["sina-global"],
            providers["iwencai"],
        ]
    if source.strip().lower() in providers:
        return [providers[source.strip().lower()]]
    raise ValueError(f"Unknown table data source: {source}")


def ordered_table_provider_chain(source: str = "auto", health_path: Path | None = None) -> list[TableProvider]:
    chain = table_provider_chain(source)
    if health_path is None:
        return chain
    store = ProviderHealthStore(health_path)
    health = store.read()
    return sorted(chain, key=lambda provider: health.get(provider.name, ProviderHealthRecord(name=provider.name)).score, reverse=True)


def fetch_with_fallback(
    symbol: str,
    start: str,
    end: str,
    adjust: str,
    source: str = "auto",
    attempts: int = 2,
    retry_sleep: float = 0.5,
) -> ProviderResult:
    errors: list[str] = []
    attempts_log: list[dict[str, str]] = []
    health_path = Path("data/provider_health.json")
    store = ProviderHealthStore(health_path)
    for provider in ordered_provider_chain(source, health_path=health_path):
        for attempt in range(1, max(attempts, 1) + 1):
            try:
                frame = provider.fetch_daily(symbol=symbol, start=start, end=end, adjust=adjust)
                _validate_daily_frame(frame, symbol)
                if not frame.empty:
                    store.update(provider.name, ok=True)
                    attempts_log.append({"provider": provider.name, "attempt": str(attempt), "status": "success", "message": f"{len(frame)} rows"})
                    return ProviderResult(provider=provider.name, frame=frame, attempts=attempts_log)
                message = "empty result"
                errors.append(f"{provider.name} attempt {attempt}: {message}")
                attempts_log.append({"provider": provider.name, "attempt": str(attempt), "status": "empty", "message": message})
                store.update(provider.name, ok=False, error=message)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider.name} attempt {attempt}: {exc}")
                attempts_log.append({"provider": provider.name, "attempt": str(attempt), "status": "failed", "message": str(exc)})
                store.update(provider.name, ok=False, error=str(exc))
            if attempt < attempts:
                sleep(retry_sleep)
    raise RuntimeError(f"All data providers failed for {symbol}: {' | '.join(errors)}")


def fetch_table_with_fallback(source: str = "auto", **kwargs: Any) -> ProviderResult:
    errors: list[str] = []
    attempts_log: list[dict[str, str]] = []
    health_path = Path("data/provider_health.json")
    store = ProviderHealthStore(health_path)
    for provider in ordered_table_provider_chain(source, health_path=health_path):
        try:
            frame = provider.fetch(**kwargs)
            if not frame.empty:
                store.update(provider.name, ok=True)
                attempts_log.append({"provider": provider.name, "attempt": "1", "status": "success", "message": f"{len(frame)} rows"})
                return ProviderResult(provider=provider.name, frame=frame, attempts=attempts_log)
            message = "empty result"
            errors.append(f"{provider.name}: {message}")
            attempts_log.append({"provider": provider.name, "attempt": "1", "status": "empty", "message": message})
            store.update(provider.name, ok=False, error=message)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{provider.name}: {exc}")
            attempts_log.append({"provider": provider.name, "attempt": "1", "status": "failed", "message": str(exc)})
            store.update(provider.name, ok=False, error=str(exc))
    raise RuntimeError(f"All table providers failed: {' | '.join(errors)}")


def _validate_daily_frame(frame: pd.DataFrame, symbol: str) -> None:
    if frame.empty:
        return
    required = ["date", "open", "high", "low", "close", "volume", "symbol"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Provider returned missing normalized columns: {missing}")
    symbols = set(frame["symbol"].astype(str).str.zfill(6).unique())
    expected = str(symbol).zfill(6)
    if symbols != {expected}:
        raise ValueError(f"Provider returned symbol mismatch for {expected}: {sorted(symbols)}")
    dates = pd.to_datetime(frame["date"], errors="coerce")
    if dates.isna().any():
        raise ValueError("Provider returned invalid dates")
    numeric = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise ValueError("Provider returned non-numeric OHLCV fields")
    bad = numeric[
        (numeric["open"] <= 0)
        | (numeric["high"] <= 0)
        | (numeric["low"] <= 0)
        | (numeric["close"] <= 0)
        | (numeric["high"] < numeric["low"])
        | (numeric["high"] < numeric[["open", "close"]].max(axis=1))
        | (numeric["low"] > numeric[["open", "close"]].min(axis=1))
        | (numeric["volume"] < 0)
    ]
    if not bad.empty:
        raise ValueError(f"Provider returned {len(bad)} invalid OHLCV rows")


def _drop_daily_placeholder_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    numeric = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    placeholder = (
        (numeric["open"] == 0)
        & (numeric["high"] == 0)
        & (numeric["low"] == 0)
        & (numeric["volume"] == 0)
        & (numeric["close"] > 0)
    )
    if not placeholder.any():
        return frame
    return frame.loc[~placeholder].copy()


def _validate_minute_frame(frame: pd.DataFrame, symbol: str) -> None:
    if frame.empty:
        return
    required = ["datetime", "open", "high", "low", "close", "volume", "symbol"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Provider returned missing normalized minute columns: {missing}")
    symbols = set(frame["symbol"].astype(str).str.zfill(6).unique())
    expected = str(symbol).zfill(6)
    if symbols != {expected}:
        raise ValueError(f"Provider returned minute symbol mismatch for {expected}: {sorted(symbols)}")
    datetimes = pd.to_datetime(frame["datetime"], errors="coerce")
    if datetimes.isna().any():
        raise ValueError("Provider returned invalid minute datetimes")
    numeric = frame[["open", "high", "low", "close", "volume"]].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise ValueError("Provider returned non-numeric minute OHLCV fields")
    bad = numeric[
        (numeric["open"] <= 0)
        | (numeric["high"] <= 0)
        | (numeric["low"] <= 0)
        | (numeric["close"] <= 0)
        | (numeric["high"] < numeric["low"])
        | (numeric["high"] < numeric[["open", "close"]].max(axis=1))
        | (numeric["low"] > numeric[["open", "close"]].min(axis=1))
        | (numeric["volume"] < 0)
    ]
    if not bad.empty:
        raise ValueError(f"Provider returned {len(bad)} invalid minute OHLCV rows")
