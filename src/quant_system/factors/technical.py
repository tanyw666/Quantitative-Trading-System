from __future__ import annotations

import pandas as pd


CORE_FACTOR_COLUMNS = (
    "ma5",
    "ma20",
    "ma20_slope_5",
    "close_to_ma20",
    "momentum_20",
    "volume_ratio_20",
    "atr_14",
    "atr_pct_14",
    "rsi_14",
    "rolling_high_20",
    "close_to_rolling_high_20",
    "traded_value",
    "trend_quality_score",
    "entry_structure_score",
    "chase_risk_score",
    "candle_warning_count",
    "volume_price_state",
    "false_breakout_flag",
    "tape_pressure_score",
    "tape_distribution_warning",
    "tape_accumulation_hint",
    "volume_confirmation_score",
    "candle_quality_score",
    "breakout_quality_score",
    "false_breakout_pressure",
)


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
    if all(column in frame.columns for column in CORE_FACTOR_COLUMNS):
        return frame.copy()

    has_symbol = "symbol" in frame.columns
    enriched = frame.copy()
    if not has_symbol:
        enriched["symbol"] = "SINGLE"
    enriched = enriched.sort_values(["symbol", "date"]).copy()
    symbols = enriched["symbol"]
    grouped_close = enriched.groupby("symbol")["close"]

    enriched["ma5"] = _rolling_mean(enriched["close"], symbols, 5, 5)
    enriched["ma20"] = _rolling_mean(enriched["close"], symbols, 20, 20)
    enriched["ma20_slope_5"] = enriched["ma20"] / enriched.groupby("symbol")["ma20"].shift(5) - 1.0
    enriched["close_to_ma20"] = enriched["close"] / enriched["ma20"] - 1.0
    enriched["momentum_20"] = enriched["close"] / grouped_close.shift(20) - 1.0

    volume_baseline = _rolling_mean(enriched["volume"], symbols, 20, 20)
    enriched["volume_ratio_20"] = enriched["volume"] / volume_baseline

    prev_close = grouped_close.shift(1)
    ranges = pd.concat(
        [
            enriched["high"] - enriched["low"],
            (enriched["high"] - prev_close).abs(),
            (enriched["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    enriched["atr_14"] = _rolling_mean(ranges, symbols, 14, 14)
    enriched["atr_pct_14"] = enriched["atr_14"] / enriched["close"]

    delta = grouped_close.diff()
    gain = _rolling_mean(delta.clip(lower=0), symbols, 14, 14)
    loss = _rolling_mean(-delta.clip(upper=0), symbols, 14, 14)
    rs = gain / loss.replace(0, pd.NA)
    enriched["rsi_14"] = 100 - (100 / (1 + rs))

    shifted_high = enriched.groupby("symbol")["high"].shift(1)
    enriched["rolling_high_20"] = _rolling_max(shifted_high, symbols, 20, 20)
    enriched["close_to_rolling_high_20"] = enriched["close"] / enriched["rolling_high_20"] - 1.0
    enriched["traded_value"] = enriched["close"] * enriched["volume"]
    _add_steady_reversal_factors_vectorized(enriched, symbols)
    _add_structure_factors(enriched)
    _add_cross_sectional_steady_reversal_score(enriched)
    if not has_symbol:
        enriched = enriched.drop(columns=["symbol"])
    enriched = enriched.sort_index()
    return enriched


def _rolling_mean(values: pd.Series, symbols: pd.Series, window: int, min_periods: int) -> pd.Series:
    return values.groupby(symbols).transform(lambda group: group.rolling(window=window, min_periods=min_periods).mean())


def _rolling_max(values: pd.Series, symbols: pd.Series, window: int, min_periods: int) -> pd.Series:
    return values.groupby(symbols).transform(lambda group: group.rolling(window=window, min_periods=min_periods).max())


def _rolling_std(values: pd.Series, symbols: pd.Series, window: int, min_periods: int) -> pd.Series:
    return values.groupby(symbols).transform(lambda group: group.rolling(window=window, min_periods=min_periods).std(ddof=0))


def _add_steady_reversal_factors_vectorized(frame: pd.DataFrame, symbols: pd.Series) -> None:
    grouped_close = frame.groupby("symbol")["close"]
    daily_return = grouped_close.pct_change()
    return_10 = frame["close"] / grouped_close.shift(10) - 1.0
    volatility_10 = _rolling_std(daily_return, symbols, 10, 10)
    frame["return_10"] = return_10
    frame["return_volatility_10"] = volatility_10
    frame["like_sharpe_10"] = return_10 / volatility_10.replace(0, pd.NA)

    amplitude = (frame["high"] - frame["low"]) / frame["close"].replace(0, pd.NA)
    frame["amplitude_10_avg"] = _rolling_mean(amplitude, symbols, 10, 10)

    turnover_source = _turnover_source(frame)
    if turnover_source is None:
        frame["turnover_60_avg"] = pd.NA
    else:
        frame["turnover_60_avg"] = _rolling_mean(turnover_source, symbols, 60, 20)


def _add_steady_reversal_factors(group: pd.DataFrame) -> None:
    daily_return = group["close"].pct_change()
    return_10 = group["close"] / group["close"].shift(10) - 1.0
    volatility_10 = daily_return.rolling(window=10, min_periods=10).std(ddof=0)
    group["return_10"] = return_10
    group["return_volatility_10"] = volatility_10
    group["like_sharpe_10"] = return_10 / volatility_10.replace(0, pd.NA)

    amplitude = (group["high"] - group["low"]) / group["close"].replace(0, pd.NA)
    group["amplitude_10_avg"] = amplitude.rolling(window=10, min_periods=10).mean()

    turnover_source = _turnover_source(group)
    if turnover_source is None:
        group["turnover_60_avg"] = pd.NA
    else:
        group["turnover_60_avg"] = turnover_source.rolling(window=60, min_periods=20).mean()


def _turnover_source(group: pd.DataFrame) -> pd.Series | None:
    for column in ("turnover", "turnover_rate", "换手率"):
        if column in group.columns:
            return pd.to_numeric(group[column], errors="coerce")
    return None


def _add_cross_sectional_steady_reversal_score(frame: pd.DataFrame) -> None:
    if frame.empty or "date" not in frame.columns:
        frame["low_turnover_z"] = pd.NA
        frame["low_amplitude_z"] = pd.NA
        frame["steady_reversal_score"] = pd.NA
        return

    frame["low_turnover_z"] = _negative_cross_sectional_zscore(frame, "turnover_60_avg")
    frame["low_amplitude_z"] = _negative_cross_sectional_zscore(frame, "amplitude_10_avg")
    frame["steady_reversal_score"] = (
        pd.to_numeric(frame["low_turnover_z"], errors="coerce").fillna(0.0)
        + pd.to_numeric(frame["low_amplitude_z"], errors="coerce").fillna(0.0)
    )


def _negative_cross_sectional_zscore(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(pd.NA, index=frame.index)
    values = pd.to_numeric(frame[column], errors="coerce")

    def score(group: pd.Series) -> pd.Series:
        std = group.std(ddof=0)
        if pd.isna(std) or float(std) == 0.0:
            return pd.Series(0.0, index=group.index)
        return -((group - group.mean()) / std)

    return values.groupby(frame["date"]).transform(score)


def _add_structure_factors(group: pd.DataFrame) -> None:
    price_range = (group["high"] - group["low"]).replace(0, pd.NA)
    body_top = pd.concat([group["open"], group["close"]], axis=1).max(axis=1)
    body_bottom = pd.concat([group["open"], group["close"]], axis=1).min(axis=1)
    close_position = ((group["close"] - group["low"]) / price_range).clip(lower=0.0, upper=1.0)
    upper_shadow = ((group["high"] - body_top) / price_range).clip(lower=0.0, upper=1.0)
    lower_shadow = ((body_bottom - group["low"]) / price_range).clip(lower=0.0, upper=1.0)
    body_pct = ((group["close"] - group["open"]).abs() / price_range).clip(lower=0.0, upper=1.0)

    group["close_position_in_range"] = close_position
    group["upper_shadow_pct"] = upper_shadow
    group["lower_shadow_pct"] = lower_shadow
    group["body_pct"] = body_pct
    group["constructive_close"] = (close_position >= 0.55).map(bool).astype(object)

    high_break = group["high"] > group["rolling_high_20"]
    close_failed = group["close"] < group["rolling_high_20"]
    heavy_volume = group["volume_ratio_20"].fillna(0) >= 1.5
    false_breakout_pressure = (
        high_break.astype(int) * 20
        + close_failed.astype(int) * 20
        + ((group["volume_ratio_20"].fillna(1.0) - 1.2).clip(lower=0.0) * 12).clip(upper=25)
        + upper_shadow.fillna(0.0) * 25
        + ((0.50 - close_position.fillna(0.5)).clip(lower=0.0) * 30)
    )
    group["false_breakout_pressure"] = pd.to_numeric(
        false_breakout_pressure.clip(lower=0.0, upper=100.0),
        errors="coerce",
    ).astype(float)
    group["false_breakout_flag"] = (
        high_break
        & close_failed
        & heavy_volume
        & ((close_position <= 0.45) | (upper_shadow >= 0.35))
    ).map(bool).astype(object)

    exhaustion = (upper_shadow >= 0.45) & (group["volume_ratio_20"].fillna(0) >= 2.0)
    weak_close = (close_position <= 0.35) & (group["volume_ratio_20"].fillna(0) >= 1.5)
    group["candle_warning_count"] = exhaustion.astype(int) + weak_close.astype(int)

    chase_from_ma = ((group["close_to_ma20"].fillna(0) - 0.10).clip(lower=0.0) * 180).clip(upper=45)
    chase_from_rsi = ((group["rsi_14"].fillna(50) - 80).clip(lower=0.0) * 1.5).clip(upper=30)
    chase_from_volume = ((group["volume_ratio_20"].fillna(1.0) - 5.0).clip(lower=0.0) * 8).clip(upper=25)
    group["chase_risk_score"] = (chase_from_ma + chase_from_rsi + chase_from_volume).clip(lower=0.0, upper=100.0)

    trend_score = (
        50
        + group["ma20_slope_5"].fillna(0) * 260
        + group["momentum_20"].fillna(0) * 70
        + (group["close"] >= group["ma20"]).astype(int) * 8
        + (close_position.fillna(0.5) - 0.5) * 12
        - group["close_to_ma20"].fillna(0).abs() * 35
    )
    group["trend_quality_score"] = pd.to_numeric(trend_score.clip(lower=0.0, upper=100.0), errors="coerce").astype(float)
    volume_confirmation_score = (
        50
        + (group["volume_ratio_20"].fillna(1.0) - 1.0) * 18
        - ((group["volume_ratio_20"].fillna(1.0) - 4.0).clip(lower=0.0) * 10)
    ).clip(lower=0.0, upper=100.0)
    candle_quality_score = (
        50
        + (close_position.fillna(0.5) - 0.5) * 60
        - upper_shadow.fillna(0.0) * 28
        + lower_shadow.fillna(0.0) * 8
    ).clip(lower=0.0, upper=100.0)
    breakout_quality_score = (
        50
        + group["close_to_rolling_high_20"].fillna(0.0) * 180
        + high_break.astype(int) * 8
        - close_failed.astype(int) * 12
        - group["false_breakout_pressure"] * 0.35
    ).clip(lower=0.0, upper=100.0)
    group["volume_confirmation_score"] = pd.to_numeric(volume_confirmation_score, errors="coerce").astype(float)
    group["candle_quality_score"] = pd.to_numeric(candle_quality_score, errors="coerce").astype(float)
    group["breakout_quality_score"] = pd.to_numeric(breakout_quality_score, errors="coerce").astype(float)
    group["entry_structure_score"] = (
        group["trend_quality_score"] * 0.45
        + volume_confirmation_score * 0.18
        + candle_quality_score * 0.20
        + breakout_quality_score * 0.17
        - group["chase_risk_score"] * 0.25
        - group["candle_warning_count"] * 8
    ).clip(lower=0.0, upper=100.0)
    group["entry_structure_score"] = pd.to_numeric(group["entry_structure_score"], errors="coerce").astype(float)
    prev_close = group.groupby("symbol")["close"].shift(1) if "symbol" in group.columns else group["close"].shift(1)
    volume_ratio_value = group["volume_ratio_20"].fillna(1.0)
    neutral_close_position = close_position.fillna(0.5)
    neutral_upper_shadow = upper_shadow.fillna(0.0)
    state = pd.Series("neutral", index=group.index, dtype=object)
    state[
        (neutral_upper_shadow >= 0.45)
        & (volume_ratio_value >= 2.0)
        & (neutral_close_position <= 0.45)
    ] = "exhaustion_warning"
    state[
        (state == "neutral")
        &
        (group["close"] > prev_close)
        & (volume_ratio_value >= 1.2)
        & (neutral_close_position >= 0.55)
    ] = "confirmed"
    state[
        (state == "neutral")
        &
        (group["close"] < prev_close)
        & (volume_ratio_value < 1.0)
        & (group["ma20"].isna() | (group["close"] >= group["ma20"]))
    ] = "quiet_pullback"
    state[group["close"].isna() | prev_close.isna()] = "neutral"
    group["volume_price_state"] = state
    group["tape_pressure_score"] = (
        (close_position.fillna(0.5) - 0.5) * 80
        + (group["volume_ratio_20"].fillna(1.0) - 1.0) * 12
        - upper_shadow.fillna(0.0) * 35
    ).clip(lower=-100.0, upper=100.0)
    group["tape_distribution_warning"] = (
        (upper_shadow >= 0.40)
        & (group["volume_ratio_20"].fillna(0) >= 1.8)
        & (close_position <= 0.40)
    ).map(bool).astype(object)
    group["tape_accumulation_hint"] = (
        (close_position >= 0.55)
        & (group["volume_ratio_20"].fillna(1.0).between(0.8, 2.5))
        & (upper_shadow <= 0.30)
    ).map(bool).astype(object)


def _volume_price_state(row: dict) -> str:
    close = row.get("close")
    prev_close = row.get("prev_close")
    volume_ratio_value = row.get("volume_ratio_20")
    close_position = row.get("close_position_in_range")
    upper_shadow = row.get("upper_shadow_pct")
    ma20 = row.get("ma20")
    if pd.isna(close) or pd.isna(prev_close):
        return "neutral"
    volume_ratio_value = 1.0 if pd.isna(volume_ratio_value) else float(volume_ratio_value)
    close_position = 0.5 if pd.isna(close_position) else float(close_position)
    upper_shadow = 0.0 if pd.isna(upper_shadow) else float(upper_shadow)
    if upper_shadow >= 0.45 and volume_ratio_value >= 2.0 and close_position <= 0.45:
        return "exhaustion_warning"
    if float(close) > float(prev_close) and volume_ratio_value >= 1.2 and close_position >= 0.55:
        return "confirmed"
    if float(close) < float(prev_close) and volume_ratio_value < 1.0 and (pd.isna(ma20) or float(close) >= float(ma20)):
        return "quiet_pullback"
    return "neutral"
