from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from quant_system.config.settings import SystemSettings
from quant_system.data.providers import fetch_table_with_fallback


@dataclass(frozen=True)
class MarketNewsItem:
    title: str
    source: str = ""
    time: str = ""
    summary: str = ""
    url: str = ""


@dataclass(frozen=True)
class MarketContext:
    as_of: str
    provider_map: dict[str, str] = field(default_factory=dict)
    global_snapshot: list[dict[str, Any]] = field(default_factory=list)
    concepts: list[dict[str, Any]] = field(default_factory=list)
    announcements: list[dict[str, Any]] = field(default_factory=list)
    news: list[dict[str, Any]] = field(default_factory=list)
    wencai: list[dict[str, Any]] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["summary_lines"] = self.summary_lines()
        return payload

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.global_snapshot:
            lines.append(f"- 全球市场：{_table_preview(self.global_snapshot, ['name', 'close', 'change_pct'])}")
        if self.concepts:
            lines.append(f"- 概念/题材线索：{_table_preview(self.concepts, ['name', 'change_pct', 'summary', 'leader', 'component_count'])}")
        valid_announcements = _filter_rows_with_any(self.announcements, ["title", "summary", "name", "symbol"])
        if valid_announcements:
            lines.append(f"- 公告提示：{_table_preview(valid_announcements, ['title', 'date', 'symbol'])}")
        elif self.announcements:
            lines.append("- 公告提示：公告源已返回数据，但未包含有效标题。")
        valid_news = _filter_rows_with_any(self.news, ["title", "summary"])
        if valid_news:
            lines.append(f"- 新闻快讯：{_table_preview(valid_news, ['title', 'summary', 'time', 'source'])}")
        if self.wencai:
            lines.append(f"- 问财样本：{_table_preview(self.wencai, ['code', 'name'])}")
        if self.signals:
            reportable_signals = [signal for signal in self.signals if _is_reportable_signal(signal)]
            lines.extend(f"- {signal}" for signal in reportable_signals[:2])
        if not lines:
            lines.append("- 暂无可用的真实市场上下文数据。")
        return _dedupe_lines(lines)[:6]


def build_market_context(settings: SystemSettings | None = None) -> MarketContext:
    settings = settings or SystemSettings()
    provider_map: dict[str, str] = {}
    as_of = date.today().isoformat()
    global_snapshot = _fetch_table_rows(settings.data_sources.global_source, "sina-global", provider_map, market="global")
    concepts = _fetch_table_rows(settings.data_sources.concept_source, "akshare-concept", provider_map)
    notice_date = date.today().strftime("%Y%m%d")
    announcements = _fetch_table_rows(
        settings.data_sources.announcement_source,
        "akshare-announcement",
        provider_map,
        symbol="全部",
        date=notice_date,
    )
    announcements = _filter_rows_with_any(announcements, ["title", "summary", "name", "symbol"])
    news = _fetch_table_rows(
        settings.data_sources.news_source,
        "akshare-news",
        provider_map,
        symbol="300059",
    )
    news = _filter_rows_with_any(news, ["title", "summary"])
    wencai = _fetch_table_rows(settings.data_sources.wencai_source, "iwencai", provider_map, query="今天涨幅居前")

    signals = _derive_signals(global_snapshot, concepts, announcements, news, wencai)
    return MarketContext(
        as_of=as_of,
        provider_map=provider_map,
        global_snapshot=global_snapshot,
        concepts=concepts,
        announcements=announcements,
        news=news,
        wencai=wencai,
        signals=signals,
    )


def _fetch_table_rows(source: str, default_source: str, provider_map: dict[str, str], **kwargs: Any) -> list[dict[str, Any]]:
    configured_source = str(source or "auto").strip().lower()
    resolved_source = default_source if configured_source in {"", "auto"} else configured_source
    try:
        result = fetch_table_with_fallback(source=resolved_source, **kwargs)
    except Exception:
        if resolved_source != default_source:
            result = fetch_table_with_fallback(source=default_source, **kwargs)
        else:
            return []
    provider_map[default_source] = result.provider
    frame = _normalize_table(result.frame)
    return frame.head(10).to_dict(orient="records")


def _normalize_table(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    rename_map = {
        "名称": "name",
        "代码": "code",
        "概念名称": "name",
        "驱动事件": "summary",
        "龙头股": "leader",
        "成分股数量": "component_count",
        "涨跌幅": "change_pct",
        "最新价": "close",
        "收盘": "close",
        "时间": "time",
        "发布时间": "time",
        "日期": "date",
        "标题": "title",
        "公告标题": "title",
        "公告日期": "date",
        "公告类型": "category",
        "tag": "source",
        "内容": "summary",
        "摘要": "summary",
        "来源": "source",
        "证券代码": "symbol",
        "证券简称": "name",
        "行业": "industry",
        "板块": "sector",
        "换手率": "turnover_rate",
        "url": "url",
        "链接": "url",
        "网址": "url",
    }
    data = data.rename(columns=rename_map)
    if "symbol" not in data.columns and "code" in data.columns:
        data["symbol"] = data["code"]
    for column in ("name", "code", "symbol", "title", "summary", "source", "time", "date", "url", "leader", "category"):
        if column in data.columns:
            data[column] = data[column].fillna("").astype(str)
    for column in ("change_pct", "close", "turnover_rate", "component_count"):
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    if "title" not in data.columns and "summary" in data.columns:
        data["title"] = data["summary"].astype(str).str.slice(0, 60)
    return data


def _derive_signals(
    global_snapshot: list[dict[str, Any]],
    concepts: list[dict[str, Any]],
    announcements: list[dict[str, Any]],
    news: list[dict[str, Any]],
    wencai: list[dict[str, Any]],
) -> list[str]:
    signals: list[str] = []
    if global_snapshot:
        best_global = next((item for item in global_snapshot if item.get("change_pct") is not None), None)
        if best_global:
            signals.append(f"全球样本 {best_global.get('name', '')} 涨跌幅 {float(best_global.get('change_pct', 0)):.2f}%")
    if concepts:
        top_concept = max(concepts, key=lambda item: float(item.get("change_pct", 0) or 0))
        if top_concept.get("change_pct") is not None:
            signals.append(f"强势概念 {top_concept.get('name', '')} {float(top_concept.get('change_pct', 0) or 0):.2f}%")
        else:
            signals.append(f"题材样本 {top_concept.get('name', '')} {top_concept.get('summary', '')}")
    if announcements:
        notice = _first_row_with_any(announcements, ["title", "summary", "name"])
        if notice:
            title = _compact_text(notice.get("title") or notice.get("summary") or notice.get("name"), 40)
            signals.append(f"重点公告：{title}")
    if news:
        item = _first_row_with_any(news, ["title", "summary"])
        if item:
            title = _compact_text(item.get("title") or item.get("summary"), 40)
            signals.append(f"重点新闻：{title}")
    if wencai:
        signals.append(f"问财样本数量 {len(wencai)}")
    return signals


def _table_preview(rows: list[dict[str, Any]], preferred_fields: list[str]) -> str:
    first = _first_row_with_any(rows, preferred_fields) or (rows[0] if rows else {})
    parts: list[str] = []
    for field in preferred_fields:
        value = first.get(field)
        if value in (None, ""):
            continue
        parts.append(f"{_field_label(field)}={_compact_text(value)}")
    return ", ".join(parts) if parts else "无有效字段"


def _compact_text(value: Any, max_chars: int = 72) -> str:
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _field_label(field: str) -> str:
    labels = {
        "name": "名称",
        "code": "代码",
        "symbol": "代码",
        "close": "收盘",
        "change_pct": "涨跌幅",
        "summary": "摘要",
        "leader": "龙头",
        "component_count": "成分数",
        "title": "标题",
        "date": "日期",
        "time": "时间",
        "source": "来源",
    }
    return labels.get(field, field)


def _is_reportable_signal(signal: str) -> bool:
    auto_prefixes = ("全球样本 ", "题材样本 ", "强势概念 ", "重点公告：", "重点新闻：", "问财样本数量 ")
    return not str(signal).startswith(auto_prefixes)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    return str(value).strip() != ""


def _first_row_with_any(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, Any] | None:
    return next((row for row in rows if any(_has_value(row.get(field)) for field in fields)), None)


def _filter_rows_with_any(rows: list[dict[str, Any]], fields: list[str]) -> list[dict[str, Any]]:
    return [row for row in rows if any(_has_value(row.get(field)) for field in fields)]


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        key = line.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result
