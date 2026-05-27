from __future__ import annotations

import pandas as pd


def moving_average(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window=window, min_periods=window).mean()


def momentum(close: pd.Series, window: int) -> pd.Series:
    return close / close.shift(window) - 1.0


def volume_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    baseline = volume.rolling(window=window, min_periods=window).mean()
    return volume / baseline


def true_range(frame: pd.DataFrame) -> pd.Series:
    prev_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    return true_range(frame).rolling(window=window, min_periods=window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=window, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).rolling(window=window, min_periods=window).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def add_core_factors(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()
    grouped = enriched.groupby("symbol", group_keys=False) if "symbol" in enriched.columns else [(None, enriched)]

    pieces = []
    for _, group in grouped:
        group = group.sort_values("date").copy()
        group["ma5"] = moving_average(group["close"], 5)
        group["ma20"] = moving_average(group["close"], 20)
        group["momentum_20"] = momentum(group["close"], 20)
        group["volume_ratio_20"] = volume_ratio(group["volume"], 20)
        group["atr_14"] = atr(group, 14)
        group["atr_pct_14"] = group["atr_14"] / group["close"]
        group["rsi_14"] = rsi(group["close"], 14)
        group["rolling_high_20"] = group["high"].shift(1).rolling(window=20, min_periods=20).max()
        pieces.append(group)

    return pd.concat(pieces).sort_index()
