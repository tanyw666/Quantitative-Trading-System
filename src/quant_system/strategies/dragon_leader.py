from __future__ import annotations

import pandas as pd

from quant_system.factors.technical import add_core_factors
from quant_system.screening.scoring import score_candidates


def infer_limit_pct(row: pd.Series) -> float:
    board = str(row.get("board", "")).upper()
    market = str(row.get("market", "")).upper()
    symbol = str(row.get("symbol", "")).zfill(6)
    if board in {"STAR", "CHINEXT"} or symbol.startswith(("688", "689", "300", "301")):
        return 0.20
    if board in {"BSE", "BJ"} or market == "BJ" or symbol.startswith(("4", "8", "9")):
        return 0.30
    return 0.10


def add_dragon_factors(frame: pd.DataFrame, tolerance: float = 0.003) -> pd.DataFrame:
    data = add_core_factors(frame)
    grouped = data.groupby("symbol", group_keys=False) if "symbol" in data.columns else [(None, data)]
    pieces = []

    for _, group in grouped:
        group = group.sort_values("date").copy()
        group["prev_close"] = group["close"].shift(1)
        group["return_1d"] = group["close"] / group["prev_close"] - 1.0
        group["open_return"] = group["open"] / group["prev_close"] - 1.0
        group["limit_pct"] = group.apply(infer_limit_pct, axis=1)
        group["limit_up_price"] = group["prev_close"] * (1 + group["limit_pct"])
        group["touch_limit_up"] = group["high"] >= group["limit_up_price"] * (1 - tolerance)
        group["is_limit_up"] = group["close"] >= group["limit_up_price"] * (1 - tolerance)
        group["failed_limit_up"] = group["touch_limit_up"] & (~group["is_limit_up"])
        group["one_price_limit_up"] = (
            group["is_limit_up"]
            & (group["open"] >= group["limit_up_price"] * (1 - tolerance))
            & (group["low"] >= group["limit_up_price"] * (1 - tolerance))
        )
        group["reseal_candidate"] = (
            group["is_limit_up"]
            & group["touch_limit_up"]
            & (~group["one_price_limit_up"])
            & (group["low"] < group["limit_up_price"] * (1 - tolerance))
        )
        price_range = (group["high"] - group["low"]).replace(0, pd.NA)
        group["close_position"] = ((group["close"] - group["low"]) / price_range).fillna(1.0).clip(0, 1)
        group["consecutive_limit_up"] = _consecutive_true(group["is_limit_up"])
        group["prev_is_limit_up"] = group["is_limit_up"].shift(1).fillna(False).astype(bool)
        group["prev_failed_limit_up"] = group["failed_limit_up"].shift(1).fillna(False).astype(bool)
        group["recent_failed_limit_up_3"] = (
            group["failed_limit_up"].shift(1).fillna(False).rolling(window=3, min_periods=1).sum()
        )
        group["failed_limit_repair"] = group["is_limit_up"] & group["prev_failed_limit_up"]

        prev_return = group["return_1d"].shift(1)
        prev_close_below_open = group["close"].shift(1) < group["open"].shift(1)
        group["weak_to_strong"] = (
            group["is_limit_up"]
            & (~group["prev_is_limit_up"])
            & ((prev_return <= 0.03) | prev_close_below_open)
            & (group["open_return"] >= -0.02)
        )
        group["high_acceptance"] = (
            group["prev_is_limit_up"]
            & (group["close_position"] >= 0.7)
            & (group["return_1d"] >= -0.03)
            & (~group["failed_limit_up"])
        )
        group["seal_quality_score"] = _seal_quality_score(group)
        group["dragon_tags"] = group.apply(lambda row: ",".join(_dragon_tags(row)), axis=1)
        group["dragon_state"] = group.apply(_dragon_state, axis=1)
        gate = group.apply(_entry_gate, axis=1)
        group["entry_gate"] = [item[0] for item in gate]
        group["entry_reasons"] = ["; ".join(item[1]) for item in gate]
        pieces.append(group)

    return pd.concat(pieces).sort_index()


def latest_dragon_diagnostics(frame: pd.DataFrame, symbol: str) -> dict:
    normalized = str(symbol).strip().zfill(6)
    data = add_dragon_factors(frame)
    if "symbol" in data.columns:
        data = data[data["symbol"].astype(str).str.zfill(6) == normalized]
    if data.empty:
        raise ValueError(f"No data found for symbol: {normalized}")

    latest = data.sort_values("date").tail(1).copy()
    latest["dragon_score"] = _dragon_score(latest)
    latest["reason"] = latest.apply(_dragon_reason, axis=1)
    return latest.iloc[0].to_dict()


def _consecutive_true(values: pd.Series) -> pd.Series:
    count = 0
    result = []
    for value in values.fillna(False):
        count = count + 1 if bool(value) else 0
        result.append(count)
    return pd.Series(result, index=values.index)


def _seal_quality_score(group: pd.DataFrame) -> pd.Series:
    score = (
        group["is_limit_up"].astype(int) * 45
        + group["touch_limit_up"].astype(int) * 15
        + group["close_position"] * 25
        + group["volume_ratio_20"].clip(lower=0, upper=3).fillna(0) / 3 * 15
        - group["failed_limit_up"].astype(int) * 35
        - group["recent_failed_limit_up_3"].clip(upper=3) * 8
    )
    return score.clip(lower=0, upper=100)


def _dragon_score(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["consecutive_limit_up"].clip(upper=5) * 15
        + frame["is_limit_up"].astype(int) * 25
        + frame["weak_to_strong"].astype(int) * 20
        + frame["failed_limit_repair"].astype(int) * 15
        + frame["reseal_candidate"].astype(int) * 8
        + frame["high_acceptance"].astype(int) * 10
        + frame["seal_quality_score"] * 0.25
        + frame["volume_ratio_20"].fillna(0).clip(upper=3) / 3 * 20
        - frame["recent_failed_limit_up_3"].clip(upper=3) * 8
    )


class DragonLeaderStrategy:
    name = "dragon_leader"

    def __init__(
        self,
        min_consecutive_limit_up: int = 2,
        min_volume_ratio: float = 1.5,
        allow_weak_to_strong: bool = True,
        entry_gate: str = "all",
        entry_model: str = "signal_day",
        max_next_open_gap: float = 0.07,
        min_next_open_gap: float = -0.03,
        require_next_open_above_ma5: bool = True,
    ) -> None:
        self.min_consecutive_limit_up = min_consecutive_limit_up
        self.min_volume_ratio = min_volume_ratio
        self.allow_weak_to_strong = allow_weak_to_strong
        self.entry_gate = entry_gate
        self.entry_model = entry_model
        self.max_next_open_gap = max_next_open_gap
        self.min_next_open_gap = min_next_open_gap
        self.require_next_open_above_ma5 = require_next_open_above_ma5

    def generate_signals(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = add_dragon_factors(frame)
        dragon_structure = data["consecutive_limit_up"] >= self.min_consecutive_limit_up
        weak_to_strong = data["weak_to_strong"] if self.allow_weak_to_strong else False
        gate_allowed = _entry_gate_mask(data["entry_gate"], self.entry_gate)
        setup_signal = (
            data["is_limit_up"]
            & (data["volume_ratio_20"] >= self.min_volume_ratio)
            & (dragon_structure | weak_to_strong)
            & gate_allowed
        )
        data["dragon_setup_signal"] = setup_signal
        next_open_ok, next_open_reasons = _next_open_entry_filter(
            data,
            max_next_open_gap=self.max_next_open_gap,
            min_next_open_gap=self.min_next_open_gap,
            require_above_ma5=self.require_next_open_above_ma5,
        )
        data["next_open_entry_ok"] = next_open_ok
        data["next_open_entry_reasons"] = next_open_reasons
        data["buy_signal"] = _entry_model_signal(data, setup_signal, self.entry_model)
        data = _carry_setup_context(data, self.entry_model)
        data["sell_signal"] = (~data["is_limit_up"]) & (data["close"] < data["ma5"])
        return data

    def screen(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = self.generate_signals(frame)
        latest = data.groupby("symbol").tail(1) if "symbol" in data.columns else data.tail(1)
        selected = latest[latest["buy_signal"]].copy()
        if not selected.empty:
            selected = _apply_setup_context(selected)
            selected["dragon_score"] = _dragon_score(selected)
            selected["reason"] = selected.apply(_dragon_reason, axis=1)
            selected = score_candidates(selected)
            selected = selected.sort_values(["dragon_score", "score"], ascending=False)

        columns = [
            col
            for col in (
                "date",
                "symbol",
                "name",
                "market",
                "board",
                "industry",
                "sector",
                "close",
                "score",
                "dragon_score",
                "risk_grade",
                "atr_stop_price",
                "is_limit_up",
                "touch_limit_up",
                "failed_limit_up",
                "one_price_limit_up",
                "reseal_candidate",
                "failed_limit_repair",
                "consecutive_limit_up",
                "weak_to_strong",
                "high_acceptance",
                "seal_quality_score",
                "recent_failed_limit_up_3",
                "close_position",
                "dragon_state",
                "dragon_tags",
                "entry_gate",
                "entry_reasons",
                "next_open_entry_ok",
                "next_open_entry_reasons",
                "limit_pct",
                "momentum_20",
                "volume_ratio_20",
                "atr_14",
                "atr_pct_14",
                "reason",
                "setup_date",
            )
            if col in selected.columns
        ]
        return selected[columns].reset_index(drop=True)


def _dragon_reason(row: pd.Series) -> str:
    labels = list(_dragon_tags(row))
    boards = int(row.get("consecutive_limit_up", 0))
    if boards > 0:
        labels.insert(0, f"{boards} boards")
    failed_count = int(row.get("recent_failed_limit_up_3", 0))
    if failed_count > 0:
        labels.append(f"{failed_count} recent failed limit-up")
    labels.append(f"seal quality {float(row.get('seal_quality_score', 0)):.1f}")
    labels.append(f"volume ratio {float(row.get('volume_ratio_20', 0)):.2f}")
    return "; ".join(labels)


def _dragon_tags(row: pd.Series) -> list[str]:
    tags = []
    if bool(row.get("one_price_limit_up", False)):
        tags.append("one-price-limit")
    if bool(row.get("reseal_candidate", False)):
        tags.append("reseal-candidate")
    if bool(row.get("failed_limit_repair", False)):
        tags.append("failed-limit-repair")
    if bool(row.get("weak_to_strong", False)):
        tags.append("weak-to-strong")
    if bool(row.get("high_acceptance", False)):
        tags.append("high-acceptance")
    if bool(row.get("failed_limit_up", False)):
        tags.append("failed-limit-up")
    return tags


def _dragon_state(row: pd.Series) -> str:
    if bool(row.get("failed_limit_up", False)):
        return "failed"
    if bool(row.get("failed_limit_repair", False)):
        return "repair"
    if bool(row.get("is_limit_up", False)):
        return "sealed"
    if bool(row.get("high_acceptance", False)):
        return "acceptance"
    return "watch"


def _entry_gate(row: pd.Series) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if bool(row.get("one_price_limit_up", False)):
        reasons.append("one-price limit-up: hard to enter without chasing")
    if float(row.get("seal_quality_score", 0)) < 60:
        reasons.append("seal quality below 60")
    if int(row.get("recent_failed_limit_up_3", 0)) >= 2:
        reasons.append("too many recent failed limit-ups")
    if bool(row.get("failed_limit_up", False)):
        reasons.append("today failed to close at limit-up")

    if reasons:
        return "block", reasons

    if int(row.get("recent_failed_limit_up_3", 0)) == 1:
        reasons.append("one recent failed limit-up")
    if float(row.get("seal_quality_score", 0)) < 80:
        reasons.append("seal quality below 80")
    if bool(row.get("is_limit_up", False)) and not bool(row.get("high_acceptance", False)):
        reasons.append("no high-acceptance confirmation")

    if reasons:
        return "watch", reasons
    return "pass", ["dragon structure passed entry gate"]


def _entry_gate_mask(values: pd.Series, policy: str) -> pd.Series:
    normalized = str(policy).strip().lower().replace("_", "-")
    if normalized == "all":
        return pd.Series(True, index=values.index)
    if normalized in {"pass-watch", "pass+watch", "exclude-block"}:
        return values.isin({"pass", "watch"})
    if normalized == "pass":
        return values == "pass"
    raise ValueError(f"Unknown dragon entry gate policy: {policy}")


def _entry_model_signal(data: pd.DataFrame, setup_signal: pd.Series, entry_model: str) -> pd.Series:
    normalized = str(entry_model).strip().lower().replace("_", "-")
    if normalized == "signal-day":
        return setup_signal
    if normalized != "next-open":
        raise ValueError(f"Unknown dragon entry model: {entry_model}")

    if "symbol" in data.columns:
        shifted = setup_signal.groupby(data["symbol"]).shift(1).fillna(False).astype(bool)
    else:
        shifted = setup_signal.shift(1).fillna(False).astype(bool)
    return shifted & data["next_open_entry_ok"]


def _carry_setup_context(data: pd.DataFrame, entry_model: str) -> pd.DataFrame:
    normalized = str(entry_model).strip().lower().replace("_", "-")
    if normalized != "next-open":
        return data

    result = data.copy()
    context_columns = [
        "date",
        "is_limit_up",
        "touch_limit_up",
        "failed_limit_up",
        "one_price_limit_up",
        "reseal_candidate",
        "failed_limit_repair",
        "consecutive_limit_up",
        "weak_to_strong",
        "high_acceptance",
        "seal_quality_score",
        "recent_failed_limit_up_3",
        "close_position",
        "dragon_state",
        "dragon_tags",
        "entry_gate",
        "entry_reasons",
        "limit_pct",
        "momentum_20",
        "volume_ratio_20",
        "atr_14",
        "atr_pct_14",
    ]
    for column in context_columns:
        if column not in result.columns:
            continue
        target = "setup_date" if column == "date" else f"setup_{column}"
        if "symbol" in result.columns:
            result[target] = result[column].groupby(result["symbol"]).shift(1)
        else:
            result[target] = result[column].shift(1)
        result.loc[~result["buy_signal"], target] = pd.NA
    return result


def _apply_setup_context(selected: pd.DataFrame) -> pd.DataFrame:
    result = selected.copy()
    for setup_column in [column for column in result.columns if column.startswith("setup_")]:
        if setup_column == "setup_date":
            continue
        target = setup_column.removeprefix("setup_")
        if target not in result.columns:
            continue
        result[target] = result[setup_column].combine_first(result[target])
    return result


def _next_open_entry_filter(
    data: pd.DataFrame,
    max_next_open_gap: float,
    min_next_open_gap: float,
    require_above_ma5: bool,
) -> tuple[pd.Series, pd.Series]:
    ok_values = []
    reason_values = []
    for row in data.to_dict(orient="records"):
        reasons = []
        open_return = float(row.get("open_return", 0) or 0)
        if open_return > max_next_open_gap:
            reasons.append("gap-too-high")
        if open_return < min_next_open_gap:
            reasons.append("gap-too-low")
        if require_above_ma5 and not pd.isna(row.get("ma5")) and float(row.get("open", 0)) < float(row.get("ma5", 0)):
            reasons.append("open-below-ma5")
        limit_up_price = row.get("limit_up_price")
        if limit_up_price is not None and not pd.isna(limit_up_price):
            if float(row.get("open", 0)) >= float(limit_up_price) * 0.999:
                reasons.append("open-at-limit-up")
        ok_values.append(not reasons)
        reason_values.append("; ".join(reasons) if reasons else "next-open entry passed")
    return pd.Series(ok_values, index=data.index), pd.Series(reason_values, index=data.index)
