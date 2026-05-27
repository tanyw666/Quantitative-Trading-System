from __future__ import annotations

import pandas as pd

from quant_system.factors.technical import add_core_factors


SECTOR_COLUMNS = ("sector", "industry", "board")


def detect_sector_column(frame: pd.DataFrame) -> str | None:
    for column in SECTOR_COLUMNS:
        if column in frame.columns:
            return column
    return None


def calculate_sector_strength(
    frame: pd.DataFrame,
    candidates: pd.DataFrame | None = None,
    sector_column: str | None = None,
    top: int = 10,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    data = frame.copy()
    if "symbol" not in data.columns:
        data["symbol"] = "SINGLE"

    sector_column = sector_column or detect_sector_column(data)
    if sector_column is None or sector_column not in data.columns:
        return pd.DataFrame()

    enriched = add_core_factors(data)
    enriched["return_1d"] = enriched.groupby("symbol")["close"].pct_change()
    latest = enriched.groupby("symbol", group_keys=False).tail(1).copy()
    latest[sector_column] = latest[sector_column].fillna("UNKNOWN").astype(str)

    candidate_counts = {}
    if candidates is not None and not candidates.empty and "symbol" in candidates.columns:
        candidate_symbols = set(candidates["symbol"].astype(str).str.zfill(6))
        latest["is_candidate"] = latest["symbol"].astype(str).str.zfill(6).isin(candidate_symbols)
    else:
        latest["is_candidate"] = False

    grouped = latest.groupby(sector_column)
    rows = []
    for sector, group in grouped:
        count = len(group)
        if count == 0:
            continue
        avg_momentum = float(group["momentum_20"].dropna().mean()) if group["momentum_20"].notna().any() else 0.0
        advance_ratio = float((group["return_1d"] > 0).mean())
        above_ma20_ratio = float((group["close"] >= group["ma20"]).mean()) if "ma20" in group else 0.0
        candidate_count = int(group["is_candidate"].sum())
        candidate_ratio = candidate_count / count
        rows.append(
            {
                "sector": sector,
                "symbol_count": count,
                "avg_momentum_20": avg_momentum,
                "advance_ratio": advance_ratio,
                "above_ma20_ratio": above_ma20_ratio,
                "candidate_count": candidate_count,
                "candidate_ratio": candidate_ratio,
            }
        )

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["strength_score"] = (
        result["avg_momentum_20"].rank(pct=True).fillna(0) * 40
        + result["advance_ratio"] * 25
        + result["above_ma20_ratio"] * 25
        + result["candidate_ratio"].clip(upper=0.2) / 0.2 * 10
    )
    return result.sort_values("strength_score", ascending=False).head(top).reset_index(drop=True)


def annotate_candidates_with_sector_strength(
    candidates: pd.DataFrame,
    sectors: pd.DataFrame,
    sector_column: str | None = None,
) -> pd.DataFrame:
    if candidates.empty or sectors.empty or "sector" not in sectors.columns:
        return candidates.copy()

    sector_column = sector_column or detect_sector_column(candidates)
    if sector_column is None or sector_column not in candidates.columns:
        return candidates.copy()

    ranked = sectors.reset_index(drop=True).copy()
    ranked["sector_rank"] = ranked.index + 1
    lookup = ranked[["sector", "strength_score", "sector_rank"]].rename(
        columns={"sector": sector_column, "strength_score": "sector_strength_score"}
    )
    enriched = candidates.merge(lookup, on=sector_column, how="left")
    enriched["sector_strength_score"] = pd.to_numeric(enriched["sector_strength_score"], errors="coerce").fillna(0.0)
    return enriched


def filter_candidates_by_top_sectors(
    candidates: pd.DataFrame,
    sectors: pd.DataFrame,
    top_n: int,
    sector_column: str | None = None,
) -> pd.DataFrame:
    if candidates.empty or sectors.empty or top_n <= 0:
        return candidates.copy()

    sector_column = sector_column or detect_sector_column(candidates)
    if sector_column is None or sector_column not in candidates.columns:
        return candidates.copy()

    top_values = set(sectors.head(top_n)["sector"].astype(str))
    filtered = candidates[candidates[sector_column].astype(str).isin(top_values)].copy()
    return filtered.reset_index(drop=True)
