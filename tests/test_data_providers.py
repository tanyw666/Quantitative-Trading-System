import pandas as pd

from quant_system.data.providers import (
    AkShareAnnouncementProvider,
    AkShareNewsProvider,
    SinaDailyProvider,
    _recent_notice_dates,
    _market_prefix,
    fetch_table_with_fallback,
    fetch_with_fallback,
    normalize_daily_bars,
    ordered_provider_chain,
    provider_chain,
    table_provider_chain,
)


def test_normalize_daily_bars_accepts_akshare_columns():
    raw = pd.DataFrame(
        {
            "\u65e5\u671f": ["2024-01-01"],
            "\u5f00\u76d8": [10],
            "\u6700\u9ad8": [11],
            "\u6700\u4f4e": [9],
            "\u6536\u76d8": [10.5],
            "\u6210\u4ea4\u91cf": [1000],
        }
    )

    frame = normalize_daily_bars(raw, "1")

    assert frame["symbol"].tolist() == ["000001"]
    assert frame["close"].tolist() == [10.5]


def test_market_prefix_supports_beijing_exchange_codes():
    assert _market_prefix("920000") == "bj"
    assert _market_prefix("830000") == "bj"
    assert _market_prefix("689009") == "sh"
    assert _market_prefix("300001") == "sz"


def test_fetch_with_fallback_uses_sina_when_akshare_fails(monkeypatch):
    class FailingAkshareProvider:
        name = "akshare"

        def fetch_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq"):
            raise RuntimeError("akshare down")

    class FakeSinaProvider(SinaDailyProvider):
        def fetch_daily(self, symbol: str, start: str, end: str, adjust: str = "qfq"):
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2024-01-01"]),
                    "open": [10],
                    "high": [11],
                    "low": [9],
                    "close": [10.5],
                    "volume": [1000],
                    "symbol": ["000001"],
                }
            )

    monkeypatch.setattr("quant_system.data.providers.provider_chain", lambda source="auto": [FailingAkshareProvider(), FakeSinaProvider()])

    result = fetch_with_fallback("000001", "20240101", "20240527", "qfq", source="akshare")

    assert result.provider == "sina"
    assert result.frame["symbol"].tolist() == ["000001"]


def test_provider_chain_auto_prefers_stable_live_sources_first():
    names = [provider.name for provider in provider_chain("auto")]
    assert names == ["sina", "tencent", "akshare", "mootdx"]


def test_table_provider_chain_auto_orders_sources():
    names = [provider.name for provider in table_provider_chain("auto")]
    assert names == ["akshare-concept", "akshare-announcement", "akshare-news", "sina-global", "iwencai"]


def test_fetch_table_with_fallback_uses_first_success(monkeypatch):
    class FailingProvider:
        name = "akshare-concept"

        def fetch(self, **kwargs):
            raise RuntimeError("down")

    class PassingProvider:
        name = "sina-global"

        def fetch(self, **kwargs):
            return pd.DataFrame({"name": ["SP500"]})

    monkeypatch.setattr("quant_system.data.providers.table_provider_chain", lambda source="auto": [FailingProvider(), PassingProvider()])
    result = fetch_table_with_fallback(source="auto")
    assert result.provider == "sina-global"


def test_akshare_news_provider_falls_back_to_global_news(monkeypatch):
    calls: list[str] = []

    def fake_fetch(method_name: str, **kwargs):
        calls.append(method_name)
        if method_name == "stock_news_em":
            raise RuntimeError("bad regex")
        return pd.DataFrame({"标题": ["快讯"], "摘要": ["摘要"], "发布时间": ["2026-05-29 09:30:00"]})

    monkeypatch.setattr("quant_system.data.providers._fetch_akshare_table", fake_fetch)

    frame = AkShareNewsProvider().fetch(symbol="300059")

    assert not frame.empty
    assert calls[:2] == ["stock_news_em", "stock_info_global_em"]


def test_akshare_announcement_provider_retries_recent_dates(monkeypatch):
    calls: list[tuple[str, str | None]] = []

    def fake_fetch(method_name: str, **kwargs):
        calls.append((method_name, kwargs.get("date")))
        if kwargs.get("date") == "20260528":
            return pd.DataFrame({"公告标题": ["公告"], "公告日期": ["2026-05-28"]})
        raise RuntimeError("empty")

    monkeypatch.setattr("quant_system.data.providers._fetch_akshare_table", fake_fetch)

    frame = AkShareAnnouncementProvider().fetch(symbol="全部", date="20260529", lookback_days=2)

    assert frame["公告标题"].tolist() == ["公告"]
    assert calls == [("stock_notice_report", "20260529"), ("stock_notice_report", "20260528")]


def test_recent_notice_dates_accepts_dash_date():
    assert _recent_notice_dates("2026-05-29", lookback_days=2) == ["20260529", "20260528"]


def test_ordered_provider_chain_uses_health_scores(tmp_path):
    health_path = tmp_path / "provider_health.json"
    health_path.write_text(
        """
{
  "akshare": {"name": "akshare", "success": 2, "failure": 10, "last_error": "bad"},
  "tencent": {"name": "tencent", "success": 10, "failure": 1, "last_error": ""}
}
""".strip(),
        encoding="utf-8",
    )
    names = [provider.name for provider in ordered_provider_chain("auto", health_path=health_path)]
    assert names[0] == "tencent"
