from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


REGIME_EXPOSURE = {
    "hot": 0.80,
    "warm": 0.60,
    "neutral": 0.30,
    "cold": 0.10,
    "frozen": 0.0,
    "empty": 0.0,
}

RISK_CAP = {
    "low": 0.20,
    "medium": 0.12,
    "high": 0.06,
    "unknown": 0.05,
}


@dataclass(frozen=True)
class AllocationItem:
    symbol: str
    name: str
    score: float
    risk_grade: str
    target_pct: float
    target_value: float
    max_pct: float
    stop_price: float | None
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AllocationPlan:
    cash: float
    regime: str
    stance: str
    target_exposure_pct: float
    target_exposure_value: float
    allocated_pct: float
    allocated_value: float
    items: list[AllocationItem]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["items"] = [item.to_dict() for item in self.items]
        return data


def build_allocation_plan(
    candidates: pd.DataFrame,
    market_temperature: dict,
    cash: float,
    max_positions: int = 5,
    regime_exposure: dict[str, float] | None = None,
    cap_by_risk: dict[str, float] | None = None,
) -> AllocationPlan:
    regime = str(market_temperature.get("regime", "empty"))
    stance = str(market_temperature.get("stance", "空仓观察"))
    regime_exposure = regime_exposure or REGIME_EXPOSURE
    cap_by_risk = cap_by_risk or RISK_CAP
    target_exposure_pct = regime_exposure.get(regime, 0.0)
    target_exposure_value = cash * target_exposure_pct

    if candidates.empty or target_exposure_pct <= 0:
        return AllocationPlan(cash, regime, stance, target_exposure_pct, target_exposure_value, 0.0, 0.0, [])

    selected = candidates.copy().head(max_positions)
    if "score" not in selected.columns:
        selected["score"] = 50.0

    selected = selected.reset_index(drop=True)
    score_weights = pd.to_numeric(selected["score"], errors="coerce").clip(lower=1).fillna(1).astype(float)
    if float(score_weights.sum()) <= 0:
        score_weights = pd.Series([1.0] * len(selected), index=selected.index, dtype="float64")

    allocated_pct_by_index = pd.Series(0.0, index=selected.index, dtype="float64")
    active_indices = set(selected.index)
    remaining_pct = float(target_exposure_pct)
    epsilon = 1e-12

    while remaining_pct > epsilon and active_indices:
        active_list = [idx for idx in selected.index if idx in active_indices]
        active_weights = score_weights.loc[active_list]
        weight_sum = float(active_weights.sum())
        if weight_sum <= 0:
            active_weights = pd.Series([1.0] * len(active_list), index=active_list, dtype="float64")
            weight_sum = float(active_weights.sum())

        round_allocated = 0.0
        next_active_indices: set[int] = set()
        for idx in active_list:
            row = selected.loc[idx]
            risk_grade = str(row.get("risk_grade", "unknown"))
            max_pct = min(cap_by_risk.get(risk_grade, cap_by_risk.get("unknown", 0.05)), remaining_pct)
            desired_pct = remaining_pct * float(active_weights.loc[idx]) / weight_sum
            target_pct = min(desired_pct, max_pct)
            if target_pct > epsilon:
                allocated_pct_by_index.loc[idx] += target_pct
                round_allocated += target_pct
            if desired_pct + epsilon < max_pct:
                next_active_indices.add(idx)

        if round_allocated <= epsilon:
            break
        remaining_pct = max(0.0, remaining_pct - round_allocated)
        active_indices = next_active_indices

    items: list[AllocationItem] = []
    allocated_pct = 0.0
    for idx, row in selected.iterrows():
        target_pct = float(allocated_pct_by_index.loc[idx])
        if target_pct <= epsilon:
            continue
        risk_grade = str(row.get("risk_grade", "unknown"))
        max_pct = cap_by_risk.get(risk_grade, cap_by_risk.get("unknown", 0.05))
        allocated_pct += target_pct
        stop_price = row.get("atr_stop_price", None)
        if pd.isna(stop_price):
            stop_price = None
        items.append(
            AllocationItem(
                symbol=str(row.get("symbol", "")),
                name=str(row.get("name", "")),
                score=float(row.get("score", 0.0)),
                risk_grade=risk_grade,
                target_pct=round(target_pct, 4),
                target_value=round(cash * target_pct, 2),
                max_pct=max_pct,
                stop_price=float(stop_price) if stop_price is not None else None,
                reason=_allocation_reason(regime, risk_grade, target_pct, max_pct),
            )
        )

    allocated_value = cash * allocated_pct
    return AllocationPlan(
        cash=cash,
        regime=regime,
        stance=stance,
        target_exposure_pct=round(target_exposure_pct, 4),
        target_exposure_value=round(target_exposure_value, 2),
        allocated_pct=round(allocated_pct, 4),
        allocated_value=round(allocated_value, 2),
        items=items,
    )


def _allocation_reason(regime: str, risk_grade: str, target_pct: float, max_pct: float) -> str:
    capped = "，已受单票风险上限约束" if target_pct >= max_pct else ""
    return f"市场状态 {regime}，个股风险 {risk_grade}{capped}"
