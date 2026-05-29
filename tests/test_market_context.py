from __future__ import annotations

import pandas as pd

from quant_system.market import context as market_context
from quant_system.market.context import MarketContext
from quant_system.data.providers import ProviderResult


def test_market_context_summary_lines_include_available_sections():
    context = MarketContext(
        as_of="2026-05-28",
        global_snapshot=[{"name": "SP500", "close": 5000, "change_pct": 1.23}],
        concepts=[{"name": "AI", "change_pct": 3.2, "turnover_rate": 12.3}],
        announcements=[{"title": "公告", "date": "2026-05-28", "symbol": "000001"}],
        news=[{"title": "新闻", "time": "09:30", "source": "akshare"}],
        wencai=[{"code": "000001", "name": "平安银行"}],
        signals=["signal-a", "signal-b"],
    )

    lines = context.summary_lines()

    assert any("全球市场" in line for line in lines)
    assert any("概念" in line for line in lines)
    assert any("公告" in line for line in lines)
    assert any("新闻" in line for line in lines)
    assert any("问财" in line for line in lines)
    assert "signal-a" in "\n".join(lines)


def test_market_context_summary_lines_ignore_blank_announcements():
    context = MarketContext(
        as_of="2026-05-28",
        announcements=[{"title": "", "summary": "", "symbol": "", "date": "2026-05-28"}],
        news=[{"title": "", "summary": "", "time": "09:30"}],
    )

    lines = context.summary_lines()

    assert any("公告源已返回数据" in line for line in lines)
    assert not any("新闻快讯" in line for line in lines)


def test_fetch_table_rows_uses_category_default_when_source_auto(monkeypatch):
    calls: list[str] = []

    def fake_fetch_table_with_fallback(source: str = "auto", **kwargs):
        calls.append(source)
        return ProviderResult(provider=source, frame=pd.DataFrame({"名称": ["AI"], "涨跌幅": [3.2]}))

    monkeypatch.setattr(market_context, "fetch_table_with_fallback", fake_fetch_table_with_fallback)

    rows = market_context._fetch_table_rows("auto", "akshare-concept", {}, query="x")

    assert calls == ["akshare-concept"]
    assert rows[0]["name"] == "AI"


def test_normalize_table_maps_announcement_columns():
    frame = market_context._normalize_table(
        pd.DataFrame(
            {
                "代码": ["688622"],
                "名称": ["*ST禾信"],
                "公告标题": ["发行股份及支付现金购买资产"],
                "公告日期": ["2026-05-29"],
                "公告类型": ["其他增发事项公告"],
                "网址": ["https://example.com"],
            }
        )
    )

    assert frame.loc[0, "symbol"] == "688622"
    assert frame.loc[0, "title"] == "发行股份及支付现金购买资产"
    assert frame.loc[0, "date"] == "2026-05-29"
    assert frame.loc[0, "category"] == "其他增发事项公告"
