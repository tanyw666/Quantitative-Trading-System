from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from quant_system.data.cache import fetch_daily_to_cache, load_daily_cache


@dataclass(frozen=True)
class DailyDataRequest:
    symbol: str
    start: str
    end: str
    cache_dir: Path = Path("data/cache/daily")
    adjust: str = "qfq"
    refresh: bool = False
    source: str = "auto"


class DailyDataRouter:
    """Cache-first daily data router.

    The router keeps research workflows reproducible by reading cached bars first.
    When refresh=True, it fetches from the configured online source and updates cache.
    """

    def load(self, request: DailyDataRequest) -> pd.DataFrame:
        if request.refresh:
            fetch_daily_to_cache(
                symbol=request.symbol,
                start_date=request.start,
                end_date=request.end,
                cache_dir=request.cache_dir,
                adjust=request.adjust,
                source=request.source,
            )
        frame = load_daily_cache(request.cache_dir, request.symbol)
        start = pd.to_datetime(request.start)
        end = pd.to_datetime(request.end)
        return frame[(frame["date"] >= start) & (frame["date"] <= end)].reset_index(drop=True)
