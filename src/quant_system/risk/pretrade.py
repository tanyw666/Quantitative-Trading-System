from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from quant_system.risk.sizing import AllocationPlan, build_allocation_plan


@dataclass(frozen=True)
class PreTradeCheck:
    name: str
    status: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PreTradeResult:
    symbol: str
    status: str
    planned_pct: float
    allowed_pct: float
    entry_price: float
    stop_price: float | None
    target_price: float | None
    stop_loss_pct: float | None
    reward_risk: float | None
    checks: list[PreTradeCheck]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["checks"] = [check.to_dict() for check in self.checks]
        return data


def run_pretrade_check(
    candidates: pd.DataFrame,
    market_temperature: dict,
    symbol: str,
    entry_price: float,
    planned_pct: float,
    cash: float,
    stop_price: float | None = None,
    target_price: float | None = None,
    max_positions: int = 5,
    regime_exposure: dict[str, float] | None = None,
    cap_by_risk: dict[str, float] | None = None,
) -> PreTradeResult:
    normalized_symbol = str(symbol).zfill(6)
    allocation = build_allocation_plan(
        candidates,
        market_temperature,
        cash=cash,
        max_positions=max_positions,
        regime_exposure=regime_exposure,
        cap_by_risk=cap_by_risk,
    )
    allowed_pct = _allowed_pct(allocation, normalized_symbol)
    checks = [
        _check_market(market_temperature),
        _check_candidate(candidates, normalized_symbol),
        _check_position_size(planned_pct, allowed_pct),
    ]

    stop_loss_pct = None
    reward_risk = None
    if stop_price is not None:
        stop_loss_pct = (entry_price - stop_price) / entry_price
        checks.append(_check_stop(entry_price, stop_price, stop_loss_pct))
    else:
        checks.append(PreTradeCheck("stop_loss", "warn", "未提供止损价，无法评估单笔风险。"))

    if target_price is not None and stop_price is not None and entry_price > stop_price:
        reward_risk = (target_price - entry_price) / (entry_price - stop_price)
        checks.append(_check_reward_risk(reward_risk))
    elif target_price is None:
        checks.append(PreTradeCheck("reward_risk", "warn", "未提供目标价，无法评估盈亏比。"))

    status = _rollup_status(checks)
    return PreTradeResult(
        symbol=normalized_symbol,
        status=status,
        planned_pct=planned_pct,
        allowed_pct=allowed_pct,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        stop_loss_pct=stop_loss_pct,
        reward_risk=reward_risk,
        checks=checks,
    )


def _allowed_pct(allocation: AllocationPlan, symbol: str) -> float:
    for item in allocation.items:
        if item.symbol == symbol:
            return item.target_pct
    return 0.0


def _check_market(market_temperature: dict) -> PreTradeCheck:
    regime = str(market_temperature.get("regime", "empty"))
    if regime in {"frozen", "empty"}:
        return PreTradeCheck("market_regime", "block", f"市场状态 {regime}，不适合开新仓。")
    if regime == "cold":
        return PreTradeCheck("market_regime", "warn", "市场偏冷，只允许极小仓位试错。")
    return PreTradeCheck("market_regime", "pass", f"市场状态 {regime}，允许按计划评估。")


def _check_candidate(candidates: pd.DataFrame, symbol: str) -> PreTradeCheck:
    if candidates.empty or "symbol" not in candidates.columns:
        return PreTradeCheck("candidate", "block", "当前没有候选池，不能开仓。")
    symbols = set(candidates["symbol"].astype(str).str.zfill(6))
    if symbol not in symbols:
        return PreTradeCheck("candidate", "block", f"{symbol} 不在当前候选池中。")
    return PreTradeCheck("candidate", "pass", f"{symbol} 在当前候选池中。")


def _check_position_size(planned_pct: float, allowed_pct: float) -> PreTradeCheck:
    if allowed_pct <= 0:
        return PreTradeCheck("position_size", "block", "系统没有给出该标的可用仓位。")
    if planned_pct > allowed_pct + 1e-12:
        return PreTradeCheck(
            "position_size",
            "block",
            f"计划仓位 {planned_pct:.1%} 超过系统上限 {allowed_pct:.1%}。",
        )
    return PreTradeCheck("position_size", "pass", f"计划仓位 {planned_pct:.1%} 未超过上限 {allowed_pct:.1%}。")


def _check_stop(entry_price: float, stop_price: float, stop_loss_pct: float) -> PreTradeCheck:
    if stop_price >= entry_price:
        return PreTradeCheck("stop_loss", "block", "止损价必须低于计划买入价。")
    if stop_loss_pct > 0.10:
        return PreTradeCheck("stop_loss", "warn", f"止损距离 {stop_loss_pct:.1%} 偏大。")
    return PreTradeCheck("stop_loss", "pass", f"止损距离 {stop_loss_pct:.1%} 可接受。")


def _check_reward_risk(reward_risk: float) -> PreTradeCheck:
    if reward_risk < 1.5:
        return PreTradeCheck("reward_risk", "warn", f"盈亏比 {reward_risk:.2f} 偏低。")
    return PreTradeCheck("reward_risk", "pass", f"盈亏比 {reward_risk:.2f} 可接受。")


def _rollup_status(checks: list[PreTradeCheck]) -> str:
    statuses = {check.status for check in checks}
    if "block" in statuses:
        return "block"
    if "warn" in statuses:
        return "warn"
    return "pass"
