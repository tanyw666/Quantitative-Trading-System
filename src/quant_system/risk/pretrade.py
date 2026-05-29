from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from quant_system.optimizer.health_labels import alert_reasons_text
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
    planned_value: float
    allowed_value: float
    entry_price: float
    stop_price: float | None
    target_price: float | None
    stop_loss_pct: float | None
    reward_risk: float | None
    max_loss_value: float | None
    expected_reward_value: float | None
    candidate_snapshot: dict | None
    checks: list[PreTradeCheck]
    action_items: list[str]
    strategy_constraint: dict | None = None

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
    strategy_health: dict | None = None,
) -> PreTradeResult:
    normalized_symbol = str(symbol).zfill(6)
    allocation = build_allocation_plan(
        candidates,
        market_temperature,
        cash=cash,
        max_positions=max_positions,
        regime_exposure=regime_exposure,
        cap_by_risk=cap_by_risk,
        strategy_health=strategy_health,
    )
    allowed_pct = _allowed_pct(allocation, normalized_symbol)
    candidate_snapshot = _candidate_snapshot(candidates, normalized_symbol)
    checks = [
        _check_market(market_temperature),
        _check_strategy_health(strategy_health),
        _check_candidate(candidates, normalized_symbol),
        _check_risk_grade(candidate_snapshot),
        _check_entry_price(candidate_snapshot, entry_price),
        _check_position_size(planned_pct, allowed_pct),
    ]

    stop_loss_pct = None
    reward_risk = None
    max_loss_value = None
    expected_reward_value = None
    planned_value = cash * planned_pct
    allowed_value = cash * allowed_pct
    if stop_price is not None:
        stop_loss_pct = (entry_price - stop_price) / entry_price
        max_loss_value = planned_value * stop_loss_pct if stop_loss_pct > 0 else None
        checks.append(_check_stop(entry_price, stop_price, stop_loss_pct))
    else:
        checks.append(PreTradeCheck("stop_loss", "warn", "未提供止损价，无法评估单笔风险。"))

    if target_price is not None and stop_price is not None and entry_price > stop_price:
        reward_risk = (target_price - entry_price) / (entry_price - stop_price)
        expected_reward_value = planned_value * ((target_price - entry_price) / entry_price)
        checks.append(_check_reward_risk(reward_risk))
    elif target_price is not None and target_price <= entry_price:
        checks.append(PreTradeCheck("reward_risk", "block", "目标价必须高于计划买入价。"))
    elif target_price is None:
        checks.append(PreTradeCheck("reward_risk", "warn", "未提供目标价，无法评估盈亏比。"))

    status = _rollup_status(checks)
    action_items = _action_items(status, checks)
    return PreTradeResult(
        symbol=normalized_symbol,
        status=status,
        planned_pct=planned_pct,
        allowed_pct=allowed_pct,
        planned_value=round(planned_value, 2),
        allowed_value=round(allowed_value, 2),
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        stop_loss_pct=stop_loss_pct,
        reward_risk=reward_risk,
        max_loss_value=round(max_loss_value, 2) if max_loss_value is not None else None,
        expected_reward_value=round(expected_reward_value, 2) if expected_reward_value is not None else None,
        candidate_snapshot=candidate_snapshot,
        checks=checks,
        action_items=action_items,
        strategy_constraint=allocation.strategy_constraint,
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


def _check_strategy_health(strategy_health: dict | None) -> PreTradeCheck:
    if not strategy_health:
        return PreTradeCheck("strategy_health", "pass", "策略健康度暂无阻断信号。")
    alert_level = str(strategy_health.get("alert_level", "pass") or "pass")
    strategy = str(strategy_health.get("strategy", "") or "")
    alerts = strategy_health.get("alerts", []) or []
    trigger_text = alert_reasons_text(alerts)
    if alert_level == "block" or strategy_health.get("action") == "pause":
        return PreTradeCheck("strategy_health", "block", f"{strategy} 策略健康度阻断，暂停新开仓。触发：{trigger_text}")
    if alert_level == "warn":
        return PreTradeCheck("strategy_health", "warn", f"{strategy} 策略健康度预警，仓位上限已降权。触发：{trigger_text}")
    return PreTradeCheck("strategy_health", "pass", f"{strategy} 策略健康度正常。")


def _check_candidate(candidates: pd.DataFrame, symbol: str) -> PreTradeCheck:
    if candidates.empty or "symbol" not in candidates.columns:
        return PreTradeCheck("candidate", "block", "当前没有候选池，不能开仓。")
    symbols = set(candidates["symbol"].astype(str).str.zfill(6))
    if symbol not in symbols:
        return PreTradeCheck("candidate", "block", f"{symbol} 不在当前候选池中。")
    return PreTradeCheck("candidate", "pass", f"{symbol} 在当前候选池中。")


def _candidate_snapshot(candidates: pd.DataFrame, symbol: str) -> dict | None:
    if candidates.empty or "symbol" not in candidates.columns:
        return None
    data = candidates.copy()
    data["symbol"] = data["symbol"].astype(str).str.zfill(6)
    matched = data[data["symbol"] == symbol]
    if matched.empty:
        return None
    row = matched.iloc[0].to_dict()
    keys = [
        "symbol",
        "name",
        "score",
        "risk_grade",
        "close",
        "atr_stop_price",
        "momentum_20",
        "volume_ratio_20",
        "reason",
        "entry_gate",
    ]
    snapshot = {}
    for key in keys:
        value = row.get(key)
        if value is not None and not pd.isna(value):
            snapshot[key] = value
    return snapshot


def _check_risk_grade(candidate: dict | None) -> PreTradeCheck:
    risk_grade = str((candidate or {}).get("risk_grade", "") or "")
    if risk_grade == "high":
        return PreTradeCheck("risk_grade", "warn", "候选风险等级为 high，只允许小仓验证。")
    if risk_grade:
        return PreTradeCheck("risk_grade", "pass", f"候选风险等级为 {risk_grade}。")
    return PreTradeCheck("risk_grade", "warn", "候选缺少风险等级，需人工确认波动和流动性。")


def _check_entry_price(candidate: dict | None, entry_price: float) -> PreTradeCheck:
    close = (candidate or {}).get("close")
    if close in (None, ""):
        return PreTradeCheck("entry_price", "pass", "候选缺少收盘价，跳过买入价偏离检查。")
    deviation = entry_price / float(close) - 1.0
    if deviation > 0.03:
        return PreTradeCheck("entry_price", "warn", f"买入价较候选收盘价高 {deviation:.1%}，注意追高。")
    if deviation < -0.08:
        return PreTradeCheck("entry_price", "warn", f"买入价较候选收盘价低 {abs(deviation):.1%}，确认是否价格输入错误。")
    return PreTradeCheck("entry_price", "pass", f"买入价相对候选收盘价偏离 {deviation:.1%}。")


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
    if stop_loss_pct < 0.01:
        return PreTradeCheck("stop_loss", "warn", f"止损距离 {stop_loss_pct:.1%} 过窄，容易被噪音扫出。")
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


def _action_items(status: str, checks: list[PreTradeCheck]) -> list[str]:
    if status == "block":
        items = ["禁止下单：先处理阻断项，再重新运行 precheck。"]
    elif status == "warn":
        items = ["允许继续观察，但下单前必须人工确认所有预警项。"]
    else:
        items = ["可按计划执行，但成交后必须写入交易日志。"]
    for check in checks:
        if check.status in {"block", "warn"}:
            items.append(f"[{check.status}] {check.message}")
    if status != "block":
        items.append("执行后记录实际成交价、数量、理由和情绪标签，盘后复盘执行偏差。")
    return items
