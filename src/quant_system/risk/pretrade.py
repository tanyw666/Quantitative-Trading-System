from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from quant_system.optimizer.health_labels import alert_reasons_text
from quant_system.risk.sizing import AllocationPlan, build_allocation_plan
from quant_system.screening.value_filters import add_value_filter_fields


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
    enriched_candidates = add_value_filter_fields(candidates)
    candidate_snapshot = _candidate_snapshot(enriched_candidates, normalized_symbol)
    checks = [
        _check_market(market_temperature),
        _check_strategy_health(strategy_health),
        _check_review_memory(strategy_health),
        _check_candidate(enriched_candidates, normalized_symbol),
        _check_risk_grade(candidate_snapshot),
        _check_value_filter(candidate_snapshot),
        _check_candidate_liquidity(candidate_snapshot),
        _check_candidate_trend_quality(candidate_snapshot),
        _check_candidate_heat(candidate_snapshot),
        _check_entry_structure(candidate_snapshot),
        _check_volume_price_confirmation(candidate_snapshot),
        _check_tape_reading(candidate_snapshot),
        _check_false_breakout(candidate_snapshot),
        _check_candle_warning(candidate_snapshot),
        _check_chase_risk(candidate_snapshot),
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


def _check_review_memory(strategy_health: dict | None) -> PreTradeCheck:
    lifecycle_pressure = (strategy_health or {}).get("lifecycle_pressure") or {}
    if not isinstance(lifecycle_pressure, dict) or not lifecycle_pressure:
        return PreTradeCheck("review_memory", "pass", "No review-memory pressure.")
    alert_level = str(lifecycle_pressure.get("alert_level", "pass") or "pass")
    action = str(lifecycle_pressure.get("action", "keep") or "keep")
    summary = str(lifecycle_pressure.get("summary", "") or "")
    if alert_level == "block" or action == "pause":
        return PreTradeCheck("review_memory", "block", f"Review memory blocks new risk: {summary}")
    if alert_level == "warn" or action == "reduce":
        return PreTradeCheck("review_memory", "warn", f"Review memory requires reduced risk: {summary}")
    return PreTradeCheck("review_memory", "pass", f"Review memory is clean: {summary}")


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
        "ma20_slope_5",
        "close_to_ma20",
        "close_to_rolling_high_20",
        "traded_value",
        "rsi_14",
        "trend_quality_score",
        "entry_structure_score",
        "chase_risk_score",
        "candle_warning_count",
        "volume_price_state",
        "false_breakout_flag",
        "false_breakout_pressure",
        "value_filter_status",
        "value_filter_reason",
        "value_warning_count",
        "st_flag",
        "delisting_risk_flag",
        "tape_pressure_score",
        "tape_distribution_warning",
        "tape_accumulation_hint",
        "close_position_in_range",
        "upper_shadow_pct",
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


def _check_value_filter(candidate: dict | None) -> PreTradeCheck:
    status = str((candidate or {}).get("value_filter_status", "") or "")
    reason = str((candidate or {}).get("value_filter_reason", "") or "")
    if status == "block":
        return PreTradeCheck("value_filter", "block", f"Value landmine filter blocks this candidate: {reason}")
    if status == "warn":
        return PreTradeCheck("value_filter", "warn", f"Value filter requires manual confirmation: {reason}")
    return PreTradeCheck("value_filter", "pass", "Value landmine filter is clean.")


def _check_candidate_liquidity(candidate: dict | None) -> PreTradeCheck:
    traded_value = (candidate or {}).get("traded_value")
    if traded_value in (None, ""):
        return PreTradeCheck("candidate_liquidity", "pass", "候选未提供成交额代理，跳过流动性硬检查。")
    value = float(traded_value)
    if value < 20_000_000:
        return PreTradeCheck("candidate_liquidity", "block", f"成交额代理仅 {value:,.0f}，流动性不足，禁止新开仓。")
    if value < 50_000_000:
        return PreTradeCheck("candidate_liquidity", "warn", f"成交额代理 {value:,.0f} 偏低，只允许小仓验证。")
    return PreTradeCheck("candidate_liquidity", "pass", f"成交额代理 {value:,.0f} 通过流动性检查。")


def _check_candidate_trend_quality(candidate: dict | None) -> PreTradeCheck:
    slope = (candidate or {}).get("ma20_slope_5")
    gap = (candidate or {}).get("close_to_ma20")
    if slope in (None, "") and gap in (None, ""):
        return PreTradeCheck("candidate_trend_quality", "pass", "候选未提供趋势质量字段，跳过趋势质量硬检查。")
    if slope not in (None, "") and float(slope) < 0:
        return PreTradeCheck("candidate_trend_quality", "block", f"MA20 五日斜率为 {float(slope):.2%}，中期趋势未走强。")
    if gap not in (None, "") and float(gap) > 0.30:
        return PreTradeCheck("candidate_trend_quality", "warn", f"价格高于 MA20 {float(gap):.1%}，追高风险偏高。")
    return PreTradeCheck("candidate_trend_quality", "pass", "趋势质量检查通过。")


def _check_candidate_heat(candidate: dict | None) -> PreTradeCheck:
    rsi = (candidate or {}).get("rsi_14")
    volume_ratio_value = (candidate or {}).get("volume_ratio_20")
    if rsi in (None, "") and volume_ratio_value in (None, ""):
        return PreTradeCheck("candidate_heat", "pass", "候选未提供热度字段，跳过过热检查。")
    if rsi not in (None, "") and float(rsi) >= 90:
        return PreTradeCheck("candidate_heat", "warn", f"RSI14 达到 {float(rsi):.1f}，短线过热，禁止追高加仓。")
    if volume_ratio_value not in (None, "") and float(volume_ratio_value) > 6:
        return PreTradeCheck("candidate_heat", "warn", f"量比 {float(volume_ratio_value):.2f} 过高，可能是一致性高潮。")
    return PreTradeCheck("candidate_heat", "pass", "候选热度未触发过热警告。")


def _check_entry_structure(candidate: dict | None) -> PreTradeCheck:
    score = (candidate or {}).get("entry_structure_score")
    if score in (None, ""):
        return PreTradeCheck("entry_structure", "pass", "Candidate has no entry structure score; skip confirmation gate.")
    value = float(score)
    if value < 40:
        return PreTradeCheck("entry_structure", "block", f"Entry structure score {value:.1f} is too weak; no fresh order.")
    if value < 55:
        return PreTradeCheck("entry_structure", "warn", f"Entry structure score {value:.1f} is marginal; require manual confirmation.")
    return PreTradeCheck("entry_structure", "pass", f"Entry structure score {value:.1f} passes confirmation gate.")


def _check_volume_price_confirmation(candidate: dict | None) -> PreTradeCheck:
    state = str((candidate or {}).get("volume_price_state", "") or "")
    if not state:
        return PreTradeCheck("volume_price_confirmation", "pass", "Candidate has no volume-price state; skip confirmation gate.")
    if state == "exhaustion_warning":
        return PreTradeCheck("volume_price_confirmation", "block", "Volume-price state shows exhaustion; wait for a cleaner setup.")
    if state == "confirmed":
        return PreTradeCheck("volume_price_confirmation", "pass", "Volume-price state confirms the entry.")
    if state == "quiet_pullback":
        return PreTradeCheck("volume_price_confirmation", "warn", "Volume-price state is a quiet pullback; only buy near support.")
    return PreTradeCheck("volume_price_confirmation", "warn", f"Volume-price state is {state}; confirmation is not strong enough.")


def _check_false_breakout(candidate: dict | None) -> PreTradeCheck:
    flag = (candidate or {}).get("false_breakout_flag")
    pressure = (candidate or {}).get("false_breakout_pressure")
    if flag in (None, "") and pressure in (None, ""):
        return PreTradeCheck("false_breakout", "pass", "Candidate has no false-breakout flag; skip confirmation gate.")
    if _as_bool(flag):
        return PreTradeCheck("false_breakout", "block", "False-breakout flag is active; do not chase this setup.")
    if pressure not in (None, "") and float(pressure) >= 55:
        return PreTradeCheck("false_breakout", "warn", f"False-breakout pressure {float(pressure):.1f} is elevated; require next-bar confirmation.")
    return PreTradeCheck("false_breakout", "pass", "False-breakout flag is clean.")


def _check_tape_reading(candidate: dict | None) -> PreTradeCheck:
    distribution = (candidate or {}).get("tape_distribution_warning")
    pressure = (candidate or {}).get("tape_pressure_score")
    if distribution not in (None, "") and _as_bool(distribution):
        return PreTradeCheck("tape_reading", "block", "Tape-reading proxy shows distribution pressure; do not open a fresh position.")
    if pressure not in (None, "") and float(pressure) < -20:
        return PreTradeCheck("tape_reading", "warn", f"Tape pressure score {float(pressure):.1f} is weak; require cleaner order-flow confirmation.")
    return PreTradeCheck("tape_reading", "pass", "Tape-reading proxy is clean.")


def _check_candle_warning(candidate: dict | None) -> PreTradeCheck:
    count = (candidate or {}).get("candle_warning_count")
    if count in (None, ""):
        return PreTradeCheck("candle_warning", "pass", "Candidate has no candle warnings; skip confirmation gate.")
    value = int(float(count))
    if value >= 2:
        return PreTradeCheck("candle_warning", "block", f"Candle warning count is {value}; structure is too noisy.")
    if value == 1:
        return PreTradeCheck("candle_warning", "warn", "One candle warning is active; reduce urgency and require manual confirmation.")
    return PreTradeCheck("candle_warning", "pass", "No candle warning is active.")


def _check_chase_risk(candidate: dict | None) -> PreTradeCheck:
    score = (candidate or {}).get("chase_risk_score")
    if score in (None, ""):
        return PreTradeCheck("chase_risk", "pass", "Candidate has no chase-risk score; skip confirmation gate.")
    value = float(score)
    if value > 70:
        return PreTradeCheck("chase_risk", "block", f"Chase-risk score {value:.1f} is extreme; do not open a new position.")
    if value > 45:
        return PreTradeCheck("chase_risk", "warn", f"Chase-risk score {value:.1f} is elevated; only allow a reduced trial position.")
    return PreTradeCheck("chase_risk", "pass", f"Chase-risk score {value:.1f} is acceptable.")


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


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


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
