from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class LiquidityFunnelConfig:
    enabled: bool = False
    mode: str = "tag"
    profile: str = "standard"
    lookback_bars: int = 250
    default_top_n: int = 800
    conservative_top_n: int = 500
    aggressive_top_n: int = 1200
    custom_top_n: int | None = None
    min_traded_value: float = 200000000.0


def limit_recent_trading_days(frame: pd.DataFrame, lookback_bars: int | None) -> pd.DataFrame:
    if not lookback_bars or lookback_bars <= 0 or frame.empty or "date" not in frame.columns:
        return frame
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"])
    dates = sorted(data["date"].dropna().dt.normalize().unique())
    if len(dates) <= lookback_bars:
        return data
    cutoff = dates[-lookback_bars]
    return data[data["date"].dt.normalize() >= cutoff].copy()


def apply_liquidity_funnel(
    candidates: pd.DataFrame,
    frame: pd.DataFrame,
    config: LiquidityFunnelConfig,
    *,
    liquidity_candidates: pd.DataFrame | None = None,
    liquidity_symbols: set[str] | None = None,
) -> pd.DataFrame:
    if candidates.empty or not config.enabled:
        return candidates.copy()

    output = candidates.copy()
    output["symbol"] = output["symbol"].astype(str).str.zfill(6)

    ranking = latest_liquidity_ranking(frame)
    ranked_by_symbol = ranking.set_index("symbol") if not ranking.empty else pd.DataFrame()
    conservative = _top_symbols(ranking, config.conservative_top_n)
    standard = _top_symbols(ranking, config.default_top_n)
    aggressive = _top_symbols(ranking, config.aggressive_top_n)
    active = _top_symbols(ranking, _active_top_n(config))
    value_pass = _value_pass_symbols(ranking, config.min_traded_value)

    external_scores: dict[str, float] = {}
    if liquidity_candidates is not None and not liquidity_candidates.empty:
        liquid = liquidity_candidates.copy()
        liquid["symbol"] = liquid["symbol"].astype(str).str.zfill(6)
        liquidity_symbols = set(liquid["symbol"])
        if "score" in liquid.columns:
            external_scores = {
                str(row["symbol"]).zfill(6): float(row["score"])
                for row in liquid[["symbol", "score"]].dropna(subset=["score"]).to_dict(orient="records")
            }
    explicit_liquidity_symbols = {str(symbol).zfill(6) for symbol in liquidity_symbols or set()}

    rows = []
    for item in output.to_dict(orient="records"):
        symbol = str(item.get("symbol", "")).zfill(6)
        rank_row = ranked_by_symbol.loc[symbol] if not ranked_by_symbol.empty and symbol in ranked_by_symbol.index else None
        traded_value = _row_value(rank_row, "traded_value")
        liquidity_rank = int(_row_value(rank_row, "liquidity_rank") or 0)
        if explicit_liquidity_symbols:
            liquidity_pass = symbol in explicit_liquidity_symbols
        else:
            liquidity_pass = symbol in active or symbol in value_pass
        conservative_pass = symbol in conservative or symbol in value_pass
        standard_pass = symbol in standard or symbol in value_pass
        aggressive_pass = symbol in aggressive or symbol in value_pass
        if explicit_liquidity_symbols:
            stage = "core_liquid" if liquidity_pass else "expansion"
        elif conservative_pass:
            stage = "core_conservative"
        elif standard_pass:
            stage = "core_standard"
        elif aggressive_pass:
            stage = "core_aggressive"
        else:
            stage = "expansion"

        score = float(item.get("score", 0) or 0)
        liquidity_score = external_scores.get(symbol)
        if liquidity_score is None:
            liquidity_score = _rank_score(ranking, liquidity_rank)
        combined_score = (score + liquidity_score) / 2 if liquidity_score else score

        item.update(
            {
                "liquidity_rank": liquidity_rank,
                "liquidity_traded_value": traded_value,
                "liquidity_conservative_pass": bool(conservative_pass),
                "liquidity_standard_pass": bool(standard_pass),
                "liquidity_aggressive_pass": bool(aggressive_pass),
                "liquidity_pass": bool(liquidity_pass),
                "liquidity_score": round(float(liquidity_score or 0), 6),
                "funnel_stage": stage,
                "combined_score": round(float(combined_score), 6),
            }
        )
        rows.append(item)

    result = pd.DataFrame(rows)
    if config.mode == "intersect":
        result = result[result["liquidity_pass"]].copy()
    if config.mode in {"tag", "boost", "intersect"} and not result.empty:
        result["_funnel_priority"] = result["funnel_stage"].map(_stage_priority).fillna(99)
        result = result.sort_values(["_funnel_priority", "combined_score"], ascending=[True, False])
        result = result.drop(columns=["_funnel_priority"])
    return result.reset_index(drop=True)


def latest_liquidity_ranking(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "symbol" not in frame.columns:
        return pd.DataFrame(columns=["symbol", "liquidity_rank", "traded_value"])
    data = frame.copy()
    data["symbol"] = data["symbol"].astype(str).str.zfill(6)
    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"])
        latest = data.sort_values(["symbol", "date"]).groupby("symbol").tail(1).copy()
    else:
        latest = data.groupby("symbol").tail(1).copy()
    latest["traded_value"] = _traded_value(latest)
    latest = latest.sort_values("traded_value", ascending=False).reset_index(drop=True)
    latest["liquidity_rank"] = latest.index + 1
    return latest[["symbol", "liquidity_rank", "traded_value"]]


def _traded_value(frame: pd.DataFrame) -> pd.Series:
    if "traded_value" in frame.columns:
        return pd.to_numeric(frame["traded_value"], errors="coerce").fillna(0)
    if "amount" in frame.columns:
        return pd.to_numeric(frame["amount"], errors="coerce").fillna(0)
    if {"close", "volume"}.issubset(frame.columns):
        return (
            pd.to_numeric(frame["close"], errors="coerce").fillna(0)
            * pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
        )
    return pd.Series(0.0, index=frame.index)


def _top_symbols(ranking: pd.DataFrame, top_n: int | None) -> set[str]:
    if ranking.empty or not top_n or top_n <= 0:
        return set()
    return set(ranking.head(int(top_n))["symbol"].astype(str))


def _value_pass_symbols(ranking: pd.DataFrame, min_traded_value: float) -> set[str]:
    if ranking.empty or min_traded_value <= 0:
        return set()
    return set(ranking[ranking["traded_value"] >= float(min_traded_value)]["symbol"].astype(str))


def _rank_score(ranking: pd.DataFrame, rank: int) -> float:
    if ranking.empty or rank <= 0:
        return 0.0
    total = max(len(ranking), 1)
    return max(0.0, 100.0 * (1.0 - (rank - 1) / total))


def _active_top_n(config: LiquidityFunnelConfig) -> int | None:
    if config.custom_top_n:
        return config.custom_top_n
    profile = str(config.profile or "standard").strip().lower()
    if profile == "conservative":
        return config.conservative_top_n
    if profile == "aggressive":
        return config.aggressive_top_n
    return config.default_top_n


def _row_value(row, column: str) -> float:
    if row is None:
        return 0.0
    try:
        return float(row[column])
    except Exception:
        return 0.0


def _stage_priority(stage: str) -> int:
    return {
        "core_conservative": 0,
        "core_liquid": 0,
        "core_standard": 1,
        "core_aggressive": 2,
        "expansion": 3,
    }.get(str(stage), 99)
