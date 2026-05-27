from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from quant_system.factors.technical import add_core_factors


@dataclass(frozen=True)
class MarketTemperature:
    score: float
    regime: str
    stance: str
    total_symbols: int
    candidate_count: int
    advance_ratio: float
    above_ma20_ratio: float
    positive_momentum_ratio: float
    candidate_ratio: float
    average_1d_return: float

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_text(self) -> str:
        return (
            f"市场温度 {self.score:.1f}/100，状态 {self.regime}，建议 {self.stance}。"
            f"上涨占比 {self.advance_ratio:.1%}，站上MA20 {self.above_ma20_ratio:.1%}，"
            f"正动量 {self.positive_momentum_ratio:.1%}，候选占比 {self.candidate_ratio:.1%}。"
        )


def calculate_market_temperature(frame: pd.DataFrame, candidates: pd.DataFrame | None = None) -> MarketTemperature:
    if frame.empty:
        return MarketTemperature(0.0, "empty", "空仓观察", 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0)

    data = frame.copy()
    if "symbol" not in data.columns:
        data["symbol"] = "SINGLE"

    enriched = add_core_factors(data)
    enriched["return_1d"] = enriched.groupby("symbol")["close"].pct_change()
    latest = enriched.groupby("symbol", group_keys=False).tail(1).copy()
    latest = latest.dropna(subset=["close"])

    total_symbols = len(latest)
    if total_symbols == 0:
        return MarketTemperature(0.0, "empty", "空仓观察", 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0)

    advance_ratio = float((latest["return_1d"] > 0).mean())
    above_ma20_ratio = float((latest["close"] >= latest["ma20"]).mean()) if "ma20" in latest else 0.0
    positive_momentum_ratio = float((latest["momentum_20"] > 0).mean()) if "momentum_20" in latest else 0.0
    average_1d_return = float(latest["return_1d"].dropna().mean()) if latest["return_1d"].notna().any() else 0.0

    candidate_count = len(candidates) if candidates is not None else 0
    candidate_ratio = candidate_count / total_symbols if total_symbols else 0.0
    normalized_candidate = min(candidate_ratio / 0.10, 1.0)

    score = (
        advance_ratio * 30
        + above_ma20_ratio * 30
        + positive_momentum_ratio * 25
        + normalized_candidate * 15
    )
    score = round(float(score), 2)
    regime, stance = classify_temperature(score)

    return MarketTemperature(
        score=score,
        regime=regime,
        stance=stance,
        total_symbols=total_symbols,
        candidate_count=candidate_count,
        advance_ratio=advance_ratio,
        above_ma20_ratio=above_ma20_ratio,
        positive_momentum_ratio=positive_momentum_ratio,
        candidate_ratio=candidate_ratio,
        average_1d_return=average_1d_return,
    )


def classify_temperature(score: float) -> tuple[str, str]:
    if score >= 75:
        return "hot", "进攻，但控制追高"
    if score >= 55:
        return "warm", "适度进攻，优先强趋势"
    if score >= 35:
        return "neutral", "轻仓试错，等待确认"
    if score >= 15:
        return "cold", "防守为主，减少交易"
    return "frozen", "空仓观察"
