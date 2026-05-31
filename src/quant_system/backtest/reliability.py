from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Iterable

import pandas as pd

from quant_system.backtest.engine import BacktestConfig, BacktestEngine
from quant_system.data.health import check_ohlcv_health
from quant_system.trace.events import DecisionEvent, DecisionRecorder


@dataclass(frozen=True)
class BacktestReliabilityConfig:
    initial_cash: float = 100000.0
    buy_price_field: str = "open"
    execution_timing: str = "next_bar"
    train_ratio: float = 0.7
    regime_lookback: int = 20
    bull_threshold: float = 0.05
    bear_threshold: float = -0.05
    min_period_rows: int = 2
    min_rows_per_symbol: int = 2
    max_stale_days: int | None = None
    as_of: str | None = None


def build_backtest_reliability_audit(
    frame: pd.DataFrame,
    strategies: Iterable[tuple[str, Any]],
    config: BacktestReliabilityConfig | None = None,
) -> dict[str, Any]:
    cfg = config or BacktestReliabilityConfig()
    data = _prepare_frame(frame)
    data_health = check_ohlcv_health(
        data,
        min_rows_per_symbol=cfg.min_rows_per_symbol,
        max_stale_days=cfg.max_stale_days,
        as_of=cfg.as_of,
    ).to_dict()
    strategy_list = list(strategies)
    if data_health.get("status") == "fail":
        return {
            "generated_at": date.today().isoformat(),
            "config": asdict(cfg),
            "data": _frame_scope(data),
            "data_health": data_health,
            "ranking": [],
            "strategies": [
                {
                    "strategy": name,
                    "ok": False,
                    "error": "Data health failed; backtest reliability audit blocked.",
                    "data_health_status": "fail",
                }
                for name, _strategy in strategy_list
            ],
        }
    reports = [_audit_strategy(data, name, strategy, cfg) for name, strategy in strategy_list]
    ranking = sorted(
        [
            {
                "strategy": item["strategy"],
                "total_return": item.get("full", {}).get("summary", {}).get("total_return", 0.0),
                "sharpe": item.get("full", {}).get("summary", {}).get("sharpe", 0.0),
                "max_drawdown": item.get("full", {}).get("summary", {}).get("max_drawdown", 0.0),
                "consistency_status": item.get("consistency", {}).get("status", "unknown"),
            }
            for item in reports
            if item.get("ok")
        ],
        key=lambda item: (float(item["total_return"]), float(item["sharpe"])),
        reverse=True,
    )
    return {
        "generated_at": date.today().isoformat(),
        "config": asdict(cfg),
        "data": _frame_scope(data),
        "data_health": data_health,
        "ranking": ranking,
        "strategies": reports,
    }


def render_backtest_reliability_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 回测可信度审计",
        "",
        f"生成日期：{payload.get('generated_at', '')}",
        f"数据健康：{(payload.get('data_health') or {}).get('status', 'unknown')}",
        "",
        "## 1. 策略横向排名",
        "",
        "| 策略 | 总收益 | 夏普 | 最大回撤 | 时序一致性 |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for item in payload.get("ranking", []):
        lines.append(
            f"| {item.get('strategy', '')} | "
            f"{float(item.get('total_return', 0) or 0):.2%} | "
            f"{float(item.get('sharpe', 0) or 0):.2f} | "
            f"{float(item.get('max_drawdown', 0) or 0):.2%} | "
            f"{item.get('consistency_status', '')} |"
        )
    if not payload.get("ranking"):
        lines.append("| 暂无 | 0.00% | 0.00 | 0.00% | unknown |")

    lines.extend(["", "## 2. 分段和成交审计", ""])
    for item in payload.get("strategies", []):
        lines.extend([f"### {item.get('strategy', '')}", ""])
        if not item.get("ok"):
            lines.extend([f"- 状态：失败", f"- 原因：{item.get('error', '')}", ""])
            continue
        full = item.get("full", {})
        summary = full.get("summary", {})
        audit = item.get("execution_audit", {})
        consistency = item.get("consistency", {})
        lines.extend(
            [
                f"- 完整区间收益：{float(summary.get('total_return', 0) or 0):.2%}",
                f"- 交易次数：{int(summary.get('trades', 0) or 0)}",
                f"- 成交阻塞次数：{int(audit.get('blocked_count', 0) or 0)}",
                f"- 信号成交一致性：{consistency.get('status', 'unknown')}",
                "",
                "| 分段 | 日期范围 | 收益 | 交易数 | 最大回撤 |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for split in item.get("splits", []):
            split_summary = split.get("summary", {})
            lines.append(
                f"| {split.get('name', '')} | "
                f"{split.get('start', '')} 至 {split.get('end', '')} | "
                f"{float(split_summary.get('total_return', 0) or 0):.2%} | "
                f"{int(split_summary.get('trades', 0) or 0)} | "
                f"{float(split_summary.get('max_drawdown', 0) or 0):.2%} |"
            )
        lines.extend(["", "| 市场环境 | 样本行数 | 收益 | 交易数 |", "| --- | ---: | ---: | ---: |"])
        for regime in item.get("regimes", []):
            regime_summary = regime.get("summary", {})
            lines.append(
                f"| {regime.get('name', '')} | "
                f"{int(regime.get('rows', 0) or 0)} | "
                f"{float(regime_summary.get('total_return', 0) or 0):.2%} | "
                f"{int(regime_summary.get('trades', 0) or 0)} |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _audit_strategy(data: pd.DataFrame, name: str, strategy: Any, cfg: BacktestReliabilityConfig) -> dict[str, Any]:
    try:
        full_result, full_events = _run_period(data, strategy, cfg)
        return {
            "strategy": name,
            "ok": True,
            "full": {"scope": _frame_scope(data), "summary": full_result.summary()},
            "splits": _split_reports(data, strategy, cfg),
            "regimes": _regime_reports(data, strategy, cfg),
            "execution_audit": summarize_execution_events(full_events),
            "consistency": summarize_signal_execution_consistency(full_result.trades, cfg.execution_timing),
        }
    except Exception as exc:
        return {"strategy": name, "ok": False, "error": str(exc)}


def summarize_execution_events(events: list[DecisionEvent]) -> dict[str, Any]:
    failed_trade_events = [event for event in events if not event.passed and event.action in {"BUY", "SELL"}]
    queued = [event for event in events if event.reason == "Signal queued for next bar execution"]
    reason_counts = Counter(event.reason for event in failed_trade_events)
    return {
        "blocked_count": len(failed_trade_events),
        "queued_count": len(queued),
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def summarize_signal_execution_consistency(trades: list, execution_timing: str = "next_bar") -> dict[str, Any]:
    missing_signal_date = 0
    same_bar_fills = 0
    future_signal_anomalies = 0
    lags: list[int] = []
    for trade in trades:
        if trade.signal_date is None:
            missing_signal_date += 1
            continue
        trade_date = pd.Timestamp(trade.date)
        signal_date = pd.Timestamp(trade.signal_date)
        lag = int((trade_date - signal_date).days)
        lags.append(lag)
        if trade_date == signal_date:
            same_bar_fills += 1
        if trade_date < signal_date or (execution_timing == "next_bar" and trade_date <= signal_date):
            future_signal_anomalies += 1

    if future_signal_anomalies:
        status = "block"
    elif missing_signal_date or (execution_timing == "next_bar" and same_bar_fills):
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "trade_count": len(trades),
        "missing_signal_date": missing_signal_date,
        "same_bar_fills": same_bar_fills,
        "future_signal_anomalies": future_signal_anomalies,
        "average_lag_days": round(sum(lags) / len(lags), 2) if lags else 0.0,
    }


def _split_reports(data: pd.DataFrame, strategy: Any, cfg: BacktestReliabilityConfig) -> list[dict[str, Any]]:
    dates = sorted(pd.to_datetime(data["date"]).dropna().unique())
    if len(dates) < 3:
        return []
    cut_index = max(min(int(len(dates) * cfg.train_ratio), len(dates) - 1), 1)
    cut_date = pd.Timestamp(dates[cut_index - 1])
    out_start = pd.Timestamp(dates[cut_index])
    splits = [
        ("in_sample", data[data["date"] <= cut_date], data[data["date"] <= cut_date], None, cut_date),
        ("out_sample", data, data[data["date"] >= out_start], out_start, None),
    ]
    return [
        _period_report(name, run_data, strategy, cfg, scope_data=scope_data, active_start=active_start, active_end=active_end)
        for name, run_data, scope_data, active_start, active_end in splits
        if len(scope_data) >= cfg.min_period_rows
    ]


def _regime_reports(data: pd.DataFrame, strategy: Any, cfg: BacktestReliabilityConfig) -> list[dict[str, Any]]:
    labels = _market_regime_by_date(data, cfg)
    reports: list[dict[str, Any]] = []
    for regime in ("bull", "range", "bear", "unknown"):
        dates = {day for day, label in labels.items() if label == regime}
        subset = data[data["date"].isin(dates)]
        if len(subset) >= cfg.min_period_rows:
            reports.append(_period_report(regime, data, strategy, cfg, scope_data=subset, active_dates=dates))
    return reports


def _period_report(
    name: str,
    subset: pd.DataFrame,
    strategy: Any,
    cfg: BacktestReliabilityConfig,
    scope_data: pd.DataFrame | None = None,
    active_start: pd.Timestamp | None = None,
    active_end: pd.Timestamp | None = None,
    active_dates: set[pd.Timestamp] | None = None,
) -> dict[str, Any]:
    run_strategy = _SignalWindowStrategy(
        strategy,
        active_start=active_start,
        active_end=active_end,
        active_dates=active_dates,
    )
    result, events = _run_period(subset, run_strategy, cfg)
    scope = _frame_scope(scope_data if scope_data is not None else subset)
    return {
        "name": name,
        **scope,
        "warmup_rows": int(max(len(subset) - len(scope_data), 0)) if scope_data is not None else 0,
        "summary": result.summary(),
        "execution_audit": summarize_execution_events(events),
        "consistency": summarize_signal_execution_consistency(result.trades, cfg.execution_timing),
    }


def _run_period(data: pd.DataFrame, strategy: Any, cfg: BacktestReliabilityConfig):
    recorder = DecisionRecorder()
    result = BacktestEngine(
        BacktestConfig(
            initial_cash=cfg.initial_cash,
            buy_price_field=cfg.buy_price_field,
            execution_timing=cfg.execution_timing,
        ),
        recorder=recorder,
    ).run(data, strategy)
    return result, recorder.events


class _SignalWindowStrategy:
    def __init__(
        self,
        strategy: Any,
        active_start: pd.Timestamp | None = None,
        active_end: pd.Timestamp | None = None,
        active_dates: set[pd.Timestamp] | None = None,
    ) -> None:
        self.strategy = strategy
        self.active_start = active_start
        self.active_end = active_end
        self.active_dates = active_dates

    def generate_signals(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = self.strategy.generate_signals(frame)
        if self.active_start is None and self.active_end is None and self.active_dates is None:
            return data
        dates = pd.to_datetime(data["date"])
        active = pd.Series(True, index=data.index)
        if self.active_dates is not None:
            active &= dates.isin(self.active_dates)
        if self.active_start is not None:
            active &= dates >= self.active_start
        if self.active_end is not None:
            active &= dates <= self.active_end
        for column in ("buy_signal", "sell_signal"):
            if column in data.columns:
                data.loc[~active, column] = False
        return data


def _market_regime_by_date(data: pd.DataFrame, cfg: BacktestReliabilityConfig) -> dict[pd.Timestamp, str]:
    index = data.groupby("date", sort=True)["close"].mean().astype(float)
    returns = index.pct_change(cfg.regime_lookback)
    labels: dict[pd.Timestamp, str] = {}
    for day, value in returns.items():
        timestamp = pd.Timestamp(day)
        if pd.isna(value):
            labels[timestamp] = "unknown"
        elif float(value) >= cfg.bull_threshold:
            labels[timestamp] = "bull"
        elif float(value) <= cfg.bear_threshold:
            labels[timestamp] = "bear"
        else:
            labels[timestamp] = "range"
    return labels


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if "symbol" not in data.columns:
        data["symbol"] = "SINGLE"
    data["date"] = pd.to_datetime(data["date"])
    return data.sort_values(["symbol", "date"]).reset_index(drop=True)


def _frame_scope(data: pd.DataFrame) -> dict[str, Any]:
    if data.empty:
        return {"rows": 0, "start": "", "end": "", "symbols": 0}
    return {
        "rows": int(len(data)),
        "start": str(pd.Timestamp(data["date"].min()).date()),
        "end": str(pd.Timestamp(data["date"].max()).date()),
        "symbols": int(data["symbol"].nunique()) if "symbol" in data.columns else 1,
    }
