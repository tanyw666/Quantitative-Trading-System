from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

from quant_system.data.cache import load_daily_cache, save_daily_cache
from quant_system.data.manifest import CacheManifest, CacheManifestEntry
from quant_system.data.providers import fetch_with_fallback
from quant_system.data.universe import read_universe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fill local daily cache from the real universe")
    parser.add_argument("--universe", type=Path, default=Path("configs/universe_real_live.csv"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache/daily"))
    parser.add_argument("--manifest", type=Path, default=Path("data/cache/manifest.jsonl"))
    parser.add_argument("--start", default="20250101")
    parser.add_argument("--end", default=None, help="End date in YYYYMMDD; defaults to today")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--chunk-size", type=int, default=0, help="Optional cap for how many missing symbols to process")
    parser.add_argument("--source-order", default="sina,tencent,mootdx,akshare")
    parser.add_argument("--refresh-all", action="store_true", help="Refresh all symbols even when cache exists")
    parser.add_argument("--refresh-stale-days", type=int, help="Refresh cached symbols older than this many calendar days")
    parser.add_argument("--print-items", action="store_true", help="Print every manifest item in the final summary")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.end = args.end or date.today().strftime("%Y%m%d")
    sources = [item.strip() for item in args.source_order.split(",") if item.strip()]
    universe = read_universe(args.universe)
    targets = target_symbols(universe, args.cache_dir, args.end, refresh_all=args.refresh_all, refresh_stale_days=args.refresh_stale_days)
    if args.chunk_size > 0:
        targets = targets[: args.chunk_size]
    print(f"targets={len(targets)} workers={args.workers} sources={sources} end={args.end}")

    manifest = CacheManifest(args.manifest)
    summary = {"ok": 0, "failed": 0, "by_provider": {}, "items": []}

    batch_size = max(args.workers * 20, 40)
    total = len(targets)
    index = 0
    while index < total:
        batch = targets[index : index + batch_size]
        with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor:
            future_map = {
                executor.submit(fetch_one, symbol, args.cache_dir, args.start, args.end, sources): symbol
                for symbol in batch
            }
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    entry = future.result()
                except Exception as exc:  # noqa: BLE001
                    entry = CacheManifestEntry(
                        symbol=symbol,
                        provider="",
                        path="",
                        start=args.start,
                        end=args.end,
                        rows=0,
                        status="failed",
                        error=str(exc),
                    )
                manifest.append(entry)
                summary["items"].append(entry.__dict__)
                if entry.status == "ok":
                    summary["ok"] += 1
                    summary["by_provider"][entry.provider] = summary["by_provider"].get(entry.provider, 0) + 1
                else:
                    summary["failed"] += 1
                index += 1
                if index % 50 == 0 or index == total:
                    print(f"progress={index}/{total} ok={summary['ok']} failed={summary['failed']}")

    cached = rebuild_cached_universe(universe, args.cache_dir)
    cached_path = args.universe.with_name("universe_cached_live.csv")
    cached.to_csv(cached_path, index=False, encoding="utf-8")
    print(f"cached_rows={len(cached)} cached_path={cached_path}")
    compact_summary = {
        "ok": summary["ok"],
        "failed": summary["failed"],
        "by_provider": summary["by_provider"],
    }
    if args.print_items:
        compact_summary["items"] = summary["items"]
    print(compact_summary)


def fetch_one(symbol: str, cache_dir: Path, start: str, end: str, sources: list[str]) -> CacheManifestEntry:
    last_error = ""
    for source in sources:
        try:
            result = fetch_with_fallback(symbol=symbol, start=start, end=end, adjust="qfq", source=source, attempts=1)
            path = save_daily_cache(cache_dir, symbol, result.frame)
            return CacheManifestEntry(
                symbol=symbol,
                provider=result.provider,
                path=str(path),
                start=start,
                end=end,
                rows=len(result.frame),
                status="ok",
                error="",
            )
        except Exception as exc:  # noqa: BLE001
            last_error = f"{source}: {exc}"
    return CacheManifestEntry(
        symbol=symbol,
        provider="",
        path="",
        start=start,
        end=end,
        rows=0,
        status="failed",
        error=last_error,
    )


def target_symbols(
    universe: list,
    cache_dir: Path,
    end: str,
    *,
    refresh_all: bool = False,
    refresh_stale_days: int | None = None,
) -> list[str]:
    targets: list[str] = []
    end_date = pd.to_datetime(end)
    for stock in universe:
        if refresh_all:
            targets.append(stock.symbol)
            continue
        try:
            frame = load_daily_cache(cache_dir, stock.symbol)
        except FileNotFoundError:
            targets.append(stock.symbol)
            continue
        if refresh_stale_days is None:
            continue
        latest = pd.to_datetime(frame["date"]).max()
        if pd.isna(latest) or int((end_date.normalize() - latest.normalize()).days) > refresh_stale_days:
            targets.append(stock.symbol)
    return targets


def rebuild_cached_universe(universe: list, cache_dir: Path) -> pd.DataFrame:
    rows = []
    for stock in universe:
        try:
            load_daily_cache(cache_dir, stock.symbol)
        except FileNotFoundError:
            continue
        rows.append(
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "market": stock.market,
                "board": stock.board,
                "industry": stock.industry,
                "sector": stock.sector,
            }
        )
    return pd.DataFrame(rows).drop_duplicates(subset=["symbol"]).sort_values("symbol")


if __name__ == "__main__":
    main()
