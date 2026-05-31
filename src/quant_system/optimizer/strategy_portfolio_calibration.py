from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from itertools import product
from typing import Any, Iterable

import pandas as pd

from quant_system.backtest.engine import BacktestConfig, BacktestEngine
from quant_system.strategies.portfolio_manager import (
    StrategyPortfolioConfig,
    StrategySleeveConfig,
    build_strategy_portfolio_plan,
)


@dataclass(frozen=True)
class PortfolioCalibrationVariant:
    name: str
    role_budget_multipliers: dict[str, float]
    duplicate_vote_bonus: float
    max_position_pct: float
    disabled_roles: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategyPortfolioBacktestStrategy:
    name = "strategy_portfolio_backtest"

    def __init__(
        self,
        config: StrategyPortfolioConfig,
        *,
        max_positions: int = 5,
        rebalance_period: int = 5,
        min_history_days: int = 30,
    ) -> None:
        self.config = config
        self.max_positions = max(int(max_positions), 1)
        self.rebalance_period = max(int(rebalance_period), 1)
        self.min_history_days = max(int(min_history_days), 1)

    def generate_signals(self, frame: pd.DataFrame) -> pd.DataFrame:
        data = _prepare_frame(frame)
        data["buy_signal"] = False
        data["sell_signal"] = False
        if data.empty:
            return data

        active_symbols: set[str] = set()
        dates = list(pd.Series(pd.to_datetime(data["date"]).drop_duplicates()).sort_values())
        for index, current_date in enumerate(dates):
            if index + 1 < self.min_history_days:
                continue
            if (index - self.min_history_days + 1) % self.rebalance_period != 0:
                continue

            history = data[data["date"] <= current_date].copy()
            plan = build_strategy_portfolio_plan(history, self.config)
            selected_symbols = set(
                plan.candidates.head(self.max_positions)["symbol"].astype(str).str.zfill(6)
                if not plan.candidates.empty and "symbol" in plan.candidates.columns
                else []
            )
            day_index = data.index[data["date"] == current_date]
            day_symbols = data.loc[day_index, "symbol"].astype(str).str.zfill(6)
            data.loc[day_index, "buy_signal"] = day_symbols.isin(selected_symbols - active_symbols).to_numpy()
            data.loc[day_index, "sell_signal"] = day_symbols.isin(active_symbols - selected_symbols).to_numpy()
            active_symbols = selected_symbols
        return data


def default_portfolio_calibration_variants(preset: str = "compact") -> list[PortfolioCalibrationVariant]:
    if preset == "full":
        variants: list[PortfolioCalibrationVariant] = []
        for attack, defensive, vote_bonus, max_position in product(
            [0.75, 1.0, 1.15],
            [0.85, 1.0, 1.25],
            [3.0, 6.0],
            [0.14, 0.20],
        ):
            variants.append(
                PortfolioCalibrationVariant(
                    name=f"attack_{attack:g}_def_{defensive:g}_vote_{vote_bonus:g}_pos_{max_position:g}",
                    role_budget_multipliers={
                        "main_attack": attack,
                        "defensive_supplement": defensive,
                        "probe": min(attack, 1.0),
                    },
                    duplicate_vote_bonus=vote_bonus,
                    max_position_pct=max_position,
                )
            )
        variants.append(
            PortfolioCalibrationVariant(
                name="no_probe_balanced",
                role_budget_multipliers={"main_attack": 1.0, "defensive_supplement": 1.0, "probe": 0.0},
                duplicate_vote_bonus=6.0,
                max_position_pct=0.16,
                disabled_roles=("probe",),
            )
        )
        return variants

    return [
        PortfolioCalibrationVariant(
            name="baseline",
            role_budget_multipliers={"main_attack": 1.0, "defensive_supplement": 1.0, "probe": 1.0},
            duplicate_vote_bonus=6.0,
            max_position_pct=0.20,
        ),
        PortfolioCalibrationVariant(
            name="balanced_lower_cap",
            role_budget_multipliers={"main_attack": 0.9, "defensive_supplement": 1.1, "probe": 0.75},
            duplicate_vote_bonus=4.0,
            max_position_pct=0.16,
        ),
        PortfolioCalibrationVariant(
            name="attack_plus",
            role_budget_multipliers={"main_attack": 1.15, "defensive_supplement": 0.9, "probe": 1.0},
            duplicate_vote_bonus=6.0,
            max_position_pct=0.20,
        ),
        PortfolioCalibrationVariant(
            name="defensive_plus",
            role_budget_multipliers={"main_attack": 0.75, "defensive_supplement": 1.25, "probe": 0.0},
            duplicate_vote_bonus=4.0,
            max_position_pct=0.14,
            disabled_roles=("probe",),
        ),
        PortfolioCalibrationVariant(
            name="no_vote_bonus",
            role_budget_multipliers={"main_attack": 1.0, "defensive_supplement": 1.0, "probe": 0.75},
            duplicate_vote_bonus=0.0,
            max_position_pct=0.16,
        ),
        PortfolioCalibrationVariant(
            name="no_probe",
            role_budget_multipliers={"main_attack": 1.0, "defensive_supplement": 1.0, "probe": 0.0},
            duplicate_vote_bonus=6.0,
            max_position_pct=0.18,
            disabled_roles=("probe",),
        ),
    ]


def run_strategy_portfolio_calibration(
    frame: pd.DataFrame,
    portfolio_config: StrategyPortfolioConfig,
    *,
    variants: Iterable[PortfolioCalibrationVariant] | None = None,
    cash: float = 100000.0,
    buy_price: str = "open",
    execution_timing: str = "next_bar",
    rebalance_period: int = 5,
    max_positions: int = 5,
    min_history_days: int = 30,
    train_ratio: float = 0.7,
) -> dict[str, Any]:
    data = _prepare_frame(frame)
    cases = [
        _evaluate_variant(
            data,
            portfolio_config,
            variant,
            cash=cash,
            buy_price=buy_price,
            execution_timing=execution_timing,
            rebalance_period=rebalance_period,
            max_positions=max_positions,
            min_history_days=min_history_days,
            train_ratio=train_ratio,
        )
        for variant in list(variants or default_portfolio_calibration_variants())
    ]
    ranked = sorted(cases, key=lambda item: _objective_key(item), reverse=True)
    return {
        "case_count": len(cases),
        "data": _frame_scope(data),
        "config": {
            "portfolio": portfolio_config.name,
            "cash": cash,
            "buy_price": buy_price,
            "execution_timing": execution_timing,
            "rebalance_period": rebalance_period,
            "max_positions": max_positions,
            "min_history_days": min_history_days,
            "train_ratio": train_ratio,
        },
        "best": ranked[0] if ranked else None,
        "baseline": next((case for case in cases if case["variant"]["name"] == "baseline"), cases[0] if cases else None),
        "cases": ranked,
        "sensitivity": _sensitivity(cases),
        "diagnosis": _diagnosis(ranked),
    }


def render_strategy_portfolio_calibration_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Strategy Portfolio Calibration",
        "",
        f"- Portfolio: {(summary.get('config') or {}).get('portfolio', '')}",
        f"- Cases: {int(summary.get('case_count', 0) or 0)}",
        f"- Data: {(summary.get('data') or {}).get('start', '')} to {(summary.get('data') or {}).get('end', '')}, "
        f"{int((summary.get('data') or {}).get('symbols', 0) or 0)} symbols",
        "",
        "## Diagnosis",
        "",
    ]
    lines.extend(f"- {item}" for item in list(summary.get("diagnosis") or []))
    best = dict(summary.get("best") or {})
    if best:
        full = dict(best.get("full") or {})
        out_sample = dict(best.get("out_sample") or {})
        lines.extend(
            [
                "",
                "## Best Variant",
                "",
                f"- Name: {(best.get('variant') or {}).get('name', '')}",
                f"- Objective: {float(best.get('objective_score', 0) or 0):.4f}",
                f"- Full return / drawdown / sharpe: "
                f"{float(full.get('total_return', 0) or 0):.2%} / "
                f"{float(full.get('max_drawdown', 0) or 0):.2%} / "
                f"{float(full.get('sharpe', 0) or 0):.2f}",
                f"- Out-sample return / drawdown / trades: "
                f"{float(out_sample.get('total_return', 0) or 0):.2%} / "
                f"{float(out_sample.get('max_drawdown', 0) or 0):.2%} / "
                f"{int(out_sample.get('trades', 0) or 0)}",
            ]
        )

    lines.extend(
        [
            "",
            "## Ranking",
            "",
            "| Rank | Variant | Objective | Full return | Out return | Drawdown | Sharpe | Trades |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, case in enumerate(list(summary.get("cases") or [])[:15], start=1):
        full = dict(case.get("full") or {})
        out_sample = dict(case.get("out_sample") or {})
        lines.append(
            f"| {index} | {(case.get('variant') or {}).get('name', '')} | "
            f"{float(case.get('objective_score', 0) or 0):.4f} | "
            f"{float(full.get('total_return', 0) or 0):.2%} | "
            f"{float(out_sample.get('total_return', 0) or 0):.2%} | "
            f"{float(full.get('max_drawdown', 0) or 0):.2%} | "
            f"{float(full.get('sharpe', 0) or 0):.2f} | "
            f"{int(full.get('trades', 0) or 0)} |"
        )

    sensitivity = dict(summary.get("sensitivity") or {})
    if sensitivity:
        lines.extend(["", "## Sensitivity", ""])
        for key, rows in sensitivity.items():
            lines.extend([f"### {key}", "", "| Value | Cases | Avg objective | Avg full return | Avg out return |", "| --- | ---: | ---: | ---: | ---: |"])
            for row in rows:
                lines.append(
                    f"| {row.get('value')} | {int(row.get('case_count', 0) or 0)} | "
                    f"{float(row.get('avg_objective_score', 0) or 0):.4f} | "
                    f"{float(row.get('avg_full_return', 0) or 0):.2%} | "
                    f"{float(row.get('avg_out_return', 0) or 0):.2%} |"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def calibrated_portfolio_config(base: StrategyPortfolioConfig, variant: PortfolioCalibrationVariant) -> StrategyPortfolioConfig:
    disabled_roles = set(variant.disabled_roles)
    sleeves: list[StrategySleeveConfig] = []
    for sleeve in base.sleeves:
        multiplier = float(variant.role_budget_multipliers.get(sleeve.role, 1.0))
        budgets = {
            regime: max(float(value) * multiplier, 0.0)
            for regime, value in sleeve.budget_pct_by_regime.items()
        }
        sleeves.append(
            replace(
                sleeve,
                enabled=sleeve.enabled and sleeve.role not in disabled_roles and multiplier > 0,
                budget_pct_by_regime=budgets,
            )
        )
    return replace(
        base,
        sleeves=tuple(sleeves),
        duplicate_vote_bonus=variant.duplicate_vote_bonus,
        max_position_pct=variant.max_position_pct,
    )


def _evaluate_variant(
    data: pd.DataFrame,
    portfolio_config: StrategyPortfolioConfig,
    variant: PortfolioCalibrationVariant,
    *,
    cash: float,
    buy_price: str,
    execution_timing: str,
    rebalance_period: int,
    max_positions: int,
    min_history_days: int,
    train_ratio: float,
) -> dict[str, Any]:
    calibrated = calibrated_portfolio_config(portfolio_config, variant)
    strategy = StrategyPortfolioBacktestStrategy(
        calibrated,
        max_positions=max_positions,
        rebalance_period=rebalance_period,
        min_history_days=min_history_days,
    )
    backtest_config = BacktestConfig(
        initial_cash=cash,
        buy_price_field=buy_price,
        execution_timing=execution_timing,
        max_position_pct=calibrated.max_position_pct,
    )
    full_result = BacktestEngine(backtest_config).run(data, strategy)
    in_frame, out_frame = _split_frame(data, train_ratio)
    in_summary = BacktestEngine(backtest_config).run(in_frame, strategy).summary() if not in_frame.empty else {}
    out_summary = BacktestEngine(backtest_config).run(out_frame, strategy).summary() if not out_frame.empty else {}
    full_summary = full_result.summary()
    objective = _objective_score(full_summary, out_summary)
    return {
        "variant": variant.to_dict(),
        "full": full_summary,
        "in_sample": in_summary,
        "out_sample": out_summary,
        "objective_score": objective,
        "trade_count": int(full_summary.get("trades", 0) or 0),
        "recommendation": _case_recommendation(full_summary, out_summary, objective),
    }


def _objective_score(full: dict[str, Any], out_sample: dict[str, Any]) -> float:
    full_return = float(full.get("total_return", 0.0) or 0.0)
    out_return = float(out_sample.get("total_return", 0.0) or 0.0)
    sharpe = float(full.get("sharpe", 0.0) or 0.0)
    drawdown = abs(float(full.get("max_drawdown", 0.0) or 0.0))
    out_drawdown = abs(float(out_sample.get("max_drawdown", 0.0) or 0.0))
    trade_count = int(full.get("trades", 0) or 0)
    trade_penalty = 0.05 if trade_count < 4 else 0.0
    return round(full_return * 0.45 + out_return * 0.35 + sharpe * 0.03 - drawdown * 0.12 - out_drawdown * 0.08 - trade_penalty, 6)


def _objective_key(case: dict[str, Any]) -> tuple[float, float, float, int]:
    full = dict(case.get("full") or {})
    out_sample = dict(case.get("out_sample") or {})
    return (
        float(case.get("objective_score", 0.0) or 0.0),
        float(out_sample.get("total_return", 0.0) or 0.0),
        -abs(float(full.get("max_drawdown", 0.0) or 0.0)),
        int(full.get("trades", 0) or 0),
    )


def _sensitivity(cases: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    keys = ("max_position_pct", "duplicate_vote_bonus")
    output: dict[str, list[dict[str, Any]]] = {}
    for key in keys:
        buckets: dict[Any, list[dict[str, Any]]] = {}
        for case in cases:
            value = (case.get("variant") or {}).get(key)
            buckets.setdefault(value, []).append(case)
        output[key] = [_summarize_bucket(value, rows) for value, rows in sorted(buckets.items(), key=lambda item: str(item[0]))]
    return output


def _summarize_bucket(value: Any, cases: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(cases)
    return {
        "value": value,
        "case_count": count,
        "avg_objective_score": sum(float(case.get("objective_score", 0) or 0) for case in cases) / count if count else 0.0,
        "avg_full_return": sum(float((case.get("full") or {}).get("total_return", 0) or 0) for case in cases) / count if count else 0.0,
        "avg_out_return": sum(float((case.get("out_sample") or {}).get("total_return", 0) or 0) for case in cases) / count if count else 0.0,
    }


def _diagnosis(cases: list[dict[str, Any]]) -> list[str]:
    if not cases:
        return ["No calibration cases were produced."]
    best = cases[0]
    baseline = next((case for case in cases if (case.get("variant") or {}).get("name") == "baseline"), None)
    notes = [
        f"Best variant: {(best.get('variant') or {}).get('name', '')}.",
    ]
    if baseline:
        delta = float(best.get("objective_score", 0) or 0) - float(baseline.get("objective_score", 0) or 0)
        notes.append(f"Best objective beats baseline by {delta:.4f}.")
    full = dict(best.get("full") or {})
    out_sample = dict(best.get("out_sample") or {})
    if int(full.get("trades", 0) or 0) < 4:
        notes.append("Best case has few trades; treat this as a smoke calibration until broader history is used.")
    if float(out_sample.get("total_return", 0) or 0) < 0:
        notes.append("Best case is weak out-of-sample; do not automatically promote it.")
    if abs(float(full.get("max_drawdown", 0) or 0)) > 0.15:
        notes.append("Best case still has drawdown above 15%; keep defensive caps enabled.")
    return notes


def _case_recommendation(full: dict[str, Any], out_sample: dict[str, Any], objective: float) -> str:
    if int(full.get("trades", 0) or 0) < 2:
        return "reject_low_trade_count"
    if float(out_sample.get("total_return", 0) or 0) < -0.05:
        return "reject_out_sample_loss"
    if objective <= 0:
        return "watch_only"
    return "candidate"


def _split_frame(data: pd.DataFrame, train_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = list(pd.Series(pd.to_datetime(data["date"]).drop_duplicates()).sort_values())
    if len(dates) < 3:
        return data.copy(), data.iloc[0:0].copy()
    cut_index = max(min(int(len(dates) * train_ratio), len(dates) - 1), 1)
    cut_date = dates[cut_index - 1]
    out_start = dates[cut_index]
    return data[data["date"] <= cut_date].copy(), data[data["date"] >= out_start].copy()


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    if "symbol" not in data.columns:
        data["symbol"] = "SINGLE"
    data["symbol"] = data["symbol"].astype(str).str.zfill(6)
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
