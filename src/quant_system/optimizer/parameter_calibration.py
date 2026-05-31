from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
from typing import Any, Iterable

import pandas as pd

from quant_system.backtest.engine import BacktestConfig, BacktestEngine
from quant_system.strategies.strong_stock_screen import StrongStockScreen


@dataclass(frozen=True)
class CalibrationCase:
    params: dict[str, Any]
    signal_count: int
    trade_count: int
    final_equity: float
    total_return: float
    max_drawdown: float
    win_rate: float
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_structure_grid() -> list[dict[str, Any]]:
    return [
        {
            "min_entry_structure_score": entry_score,
            "max_chase_risk_score": chase_score,
            "max_candle_warning_count": candle_count,
            "block_false_breakout": block_false,
        }
        for entry_score, chase_score, candle_count, block_false in product(
            [0.0, 45.0, 55.0, 65.0],
            [35.0, 45.0, 60.0, 100.0],
            [0, 1],
            [True, False],
        )
    ]


def run_structure_parameter_calibration(
    frame: pd.DataFrame,
    *,
    grid: Iterable[dict[str, Any]] | None = None,
    base_params: dict[str, Any] | None = None,
    backtest_config: BacktestConfig | None = None,
) -> dict[str, Any]:
    grid_items = list(grid or default_structure_grid())
    base_params = dict(base_params or {})
    config = backtest_config or BacktestConfig(
        initial_cash=100000,
        max_position_pct=0.2,
        commission_rate=0.0003,
        slippage_rate=0.0005,
        execution_timing="next_bar",
    )
    cases: list[CalibrationCase] = []
    for item in grid_items:
        params = {**base_params, **item}
        strategy = StrongStockScreen(**params)
        signals = strategy.generate_signals(frame)
        signal_count = int(signals["buy_signal"].fillna(False).sum()) if "buy_signal" in signals else 0
        result = BacktestEngine(config).run(frame, strategy)
        summary = result.summary()
        cases.append(
            CalibrationCase(
                params=params,
                signal_count=signal_count,
                trade_count=len(result.trades),
                final_equity=float(summary.get("final_equity", config.initial_cash) or config.initial_cash),
                total_return=float(summary.get("total_return", 0.0) or 0.0),
                max_drawdown=float(summary.get("max_drawdown", 0.0) or 0.0),
                win_rate=float(summary.get("win_rate", 0.0) or 0.0),
                note=_case_note(signal_count, len(result.trades), params),
            )
        )
    ranked = sorted(cases, key=lambda case: (case.final_equity, case.win_rate, -case.max_drawdown), reverse=True)
    return {
        "case_count": len(cases),
        "baseline": cases[0].to_dict() if cases else None,
        "best": ranked[0].to_dict() if ranked else None,
        "worst": ranked[-1].to_dict() if ranked else None,
        "zero_signal_count": sum(1 for case in cases if case.signal_count == 0),
        "zero_trade_count": sum(1 for case in cases if case.trade_count == 0),
        "sensitivity": _sensitivity_analysis(cases),
        "cases": [case.to_dict() for case in ranked],
        "diagnosis": _diagnosis(ranked),
    }


def render_calibration_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Structure Parameter Calibration",
        "",
        f"- Cases: {int(summary.get('case_count', 0) or 0)}",
        f"- Zero-signal cases: {int(summary.get('zero_signal_count', 0) or 0)}",
        f"- Zero-trade cases: {int(summary.get('zero_trade_count', 0) or 0)}",
        "",
        "## Diagnosis",
        "",
    ]
    lines.extend(f"- {item}" for item in list(summary.get("diagnosis") or []))
    best = dict(summary.get("best") or {})
    if best:
        lines.extend(
            [
                "",
                "## Best Case",
                "",
                f"- Params: {best.get('params', {})}",
                f"- Signals / trades: {int(best.get('signal_count', 0) or 0)} / {int(best.get('trade_count', 0) or 0)}",
                f"- Total return: {float(best.get('total_return', 0) or 0):.2%}",
                f"- Max drawdown: {float(best.get('max_drawdown', 0) or 0):.2%}",
                f"- Win rate: {float(best.get('win_rate', 0) or 0):.1%}",
                f"- Note: {best.get('note', '')}",
            ]
        )
    sensitivity = dict(summary.get("sensitivity") or {})
    if sensitivity:
        lines.extend(["", "## Threshold Sensitivity", ""])
        for parameter, rows in sensitivity.items():
            lines.extend(
                [
                    f"### {parameter}",
                    "",
                    "| Value | Cases | Avg signals | Avg trades | Avg return | Avg win rate | Zero-signal rate |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for row in rows:
                lines.append(
                    f"| {row.get('value')} | {int(row.get('case_count', 0) or 0)} | "
                    f"{float(row.get('avg_signal_count', 0) or 0):.1f} | "
                    f"{float(row.get('avg_trade_count', 0) or 0):.1f} | "
                    f"{float(row.get('avg_total_return', 0) or 0):.2%} | "
                    f"{float(row.get('avg_win_rate', 0) or 0):.1%} | "
                    f"{float(row.get('zero_signal_rate', 0) or 0):.1%} |"
                )
            lines.append("")
    cases = list(summary.get("cases") or [])[:10]
    if cases:
        lines.extend(["", "## Top Cases", "", "| Rank | Entry score | Chase cap | Candle cap | False breakout | Signals | Trades | Return | Drawdown |", "| ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |"])
        for idx, case in enumerate(cases, start=1):
            params = dict(case.get("params") or {})
            lines.append(
                f"| {idx} | {float(params.get('min_entry_structure_score', 0) or 0):.0f} | "
                f"{float(params.get('max_chase_risk_score', 0) or 0):.0f} | "
                f"{int(params.get('max_candle_warning_count', 0) or 0)} | "
                f"{bool(params.get('block_false_breakout'))} | "
                f"{int(case.get('signal_count', 0) or 0)} | "
                f"{int(case.get('trade_count', 0) or 0)} | "
                f"{float(case.get('total_return', 0) or 0):.2%} | "
                f"{float(case.get('max_drawdown', 0) or 0):.2%} |"
            )
    return "\n".join(lines)


def _sensitivity_analysis(cases: list[CalibrationCase]) -> dict[str, list[dict[str, Any]]]:
    parameters = (
        "min_entry_structure_score",
        "max_chase_risk_score",
        "max_candle_warning_count",
        "block_false_breakout",
    )
    analysis: dict[str, list[dict[str, Any]]] = {}
    for parameter in parameters:
        buckets: dict[Any, list[CalibrationCase]] = {}
        for case in cases:
            value = case.params.get(parameter)
            buckets.setdefault(value, []).append(case)
        rows = [_summarize_bucket(value, bucket) for value, bucket in buckets.items()]
        analysis[parameter] = sorted(rows, key=lambda row: str(row["value"]))
    return analysis


def _summarize_bucket(value: Any, cases: list[CalibrationCase]) -> dict[str, Any]:
    count = len(cases)
    if count <= 0:
        return {
            "value": value,
            "case_count": 0,
            "avg_signal_count": 0.0,
            "avg_trade_count": 0.0,
            "avg_total_return": 0.0,
            "avg_max_drawdown": 0.0,
            "avg_win_rate": 0.0,
            "zero_signal_rate": 0.0,
            "zero_trade_rate": 0.0,
        }
    return {
        "value": value,
        "case_count": count,
        "avg_signal_count": sum(case.signal_count for case in cases) / count,
        "avg_trade_count": sum(case.trade_count for case in cases) / count,
        "avg_total_return": sum(case.total_return for case in cases) / count,
        "avg_max_drawdown": sum(case.max_drawdown for case in cases) / count,
        "avg_win_rate": sum(case.win_rate for case in cases) / count,
        "zero_signal_rate": sum(1 for case in cases if case.signal_count == 0) / count,
        "zero_trade_rate": sum(1 for case in cases if case.trade_count == 0) / count,
    }


def _case_note(signal_count: int, trade_count: int, params: dict[str, Any]) -> str:
    if signal_count == 0:
        return "too_strict_no_signal"
    if trade_count == 0:
        return "signals_not_executable"
    if float(params.get("min_entry_structure_score", 0) or 0) >= 65 and float(params.get("max_chase_risk_score", 100) or 100) <= 35:
        return "strict_structure_and_chase"
    if not bool(params.get("block_false_breakout", True)):
        return "false_breakout_filter_disabled"
    return "normal"


def _diagnosis(cases: list[CalibrationCase]) -> list[str]:
    if not cases:
        return ["No calibration cases were produced."]
    notes: list[str] = []
    zero_signal_count = sum(1 for case in cases if case.signal_count == 0)
    if zero_signal_count / len(cases) >= 0.5:
        notes.append("Many parameter combinations produced no signals; thresholds may be too strict for this sample.")
    zero_trade_count = sum(1 for case in cases if case.trade_count == 0)
    if zero_trade_count / len(cases) >= 0.5:
        notes.append("Many signal combinations produced no trades; execution rules or next-bar data may be restrictive.")
    best = cases[0]
    if best.trade_count < 3:
        notes.append("Best case has fewer than three trades; treat the result as a smoke test, not statistical proof.")
    if best.max_drawdown < -0.1:
        notes.append("Best case still has drawdown above 10%; do not loosen risk filters without more samples.")
    if not notes:
        notes.append("Calibration sample produced usable signals; compare the top cases on larger history before changing defaults.")
    return notes
