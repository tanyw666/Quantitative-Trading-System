from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from quant_system.config.settings import load_settings
from quant_system.config.settings import SystemSettings
from quant_system.backtest.engine import BacktestConfig, BacktestEngine
from quant_system.backtest.reliability import (
    BacktestReliabilityConfig,
    build_backtest_reliability_audit,
    render_backtest_reliability_markdown,
)
from quant_system.data.cache import fetch_daily_to_cache, load_daily_cache, save_daily_cache
from quant_system.data.csv_source import read_ohlcv_csv
from quant_system.data.dataset import load_ohlcv_dataset
from quant_system.data.health import build_ohlcv_repair_plan, check_ohlcv_health
from quant_system.data.manifest import CacheManifest, CacheManifestEntry
from quant_system.data.providers import (
    AkShareAdjustmentFactorProvider,
    AkShareMinuteProvider,
    ProviderResult,
    fetch_table_with_fallback,
    fetch_with_fallback,
    minute_provider_chain,
    provider_chain,
)
from quant_system.data.universe import read_universe
from quant_system.data.universe_builder import UniverseBuildOptions, fetch_akshare_universe, filter_universe, save_universe
from quant_system.factors.technical import add_core_factors
from quant_system.market.temperature import calculate_market_temperature
from quant_system.market.context import build_market_context
from quant_system.market.sectors import (
    annotate_candidates_with_sector_strength,
    calculate_sector_strength,
    filter_candidates_by_top_sectors,
)
from quant_system.optimizer.experiments import load_experiment_cases, preset_cases, run_parameter_experiments
from quant_system.optimizer.parameter_calibration import (
    render_calibration_markdown,
    run_structure_parameter_calibration,
)
from quant_system.optimizer.strategy_portfolio_calibration import (
    default_portfolio_calibration_variants,
    render_strategy_portfolio_calibration_markdown,
    run_strategy_portfolio_calibration,
)
from quant_system.optimizer.export_strategy import (
    load_experiment_summary,
    strategy_config_from_summary,
    write_strategy_config,
)
from quant_system.optimizer.promotion import (
    append_promotion_record,
    persist_promotion_record,
    promote_strategy_from_summary,
    read_promotion_records,
    summarize_promotion_records,
)
from quant_system.optimizer.health import summarize_strategy_health
from quant_system.optimizer.strategy_validation import validate_strategy_config, validate_strategy_directory
from quant_system.optimizer.selection_validation import (
    summarize_forward_returns,
    summarize_forward_returns_by,
    validate_selections,
    validate_selection_file,
)
from quant_system.portfolio.discipline import (
    build_discipline_record,
    persist_discipline_record,
    read_discipline_records,
    summarize_discipline_records,
)
from quant_system.portfolio.discipline_adherence import evaluate_discipline_adherence
from quant_system.portfolio.trade_plan import build_trade_plan, build_trade_plan_batch, render_trade_plan_markdown
from quant_system.portfolio.trade_plan import (
    append_unique_trade_plan_records,
    append_trade_plan_record,
    read_trade_plan_records,
    render_trade_plan_batch_markdown,
    render_trade_plan_summary_markdown,
    summarize_trade_plan_records,
)
from quant_system.portfolio.trade_plan_audit import (
    render_trade_plan_audit_markdown,
    render_trade_plan_audit_lines,
    summarize_trade_plan_audit,
)
from quant_system.portfolio.execution_audit import render_execution_audit_markdown, summarize_execution_audit
from quant_system.portfolio.approval_execution import (
    render_approval_execution_markdown,
    summarize_approval_execution,
)
from quant_system.portfolio.order_approval import (
    append_order_approval_record,
    build_order_approval,
    read_order_approval_records,
    render_order_approval_markdown,
    render_order_approval_summary_markdown,
    summarize_order_approvals,
)
from quant_system.portfolio.trading_day_state import (
    append_trading_day_state_record,
    apply_trading_day_template,
    build_trading_day_state,
    read_trading_day_state_records,
    render_trading_day_state_history_markdown,
    summarize_trading_day_state_records,
)
from quant_system.portfolio.trading_day_watchdog import (
    build_trading_day_watchdog,
    render_trading_day_watchdog_markdown,
)
from quant_system.portfolio.journal import (
    TradeJournal,
    TradeJournalEntry,
    summarize_discipline_exceptions,
    summarize_gate_journal,
    summarize_trade_journal,
)
from quant_system.portfolio.positions import build_position_book
from quant_system.portfolio.lots import (
    append_lot_book_record,
    build_lot_book,
    render_lot_book_markdown,
)
from quant_system.portfolio.lifecycle_pressure import (
    build_lifecycle_pressure,
    build_review_memory_pressure,
)
from quant_system.portfolio.lifecycle_rules import build_lifecycle_rule_plan
from quant_system.portfolio.action_execution import (
    render_action_execution_lines,
    render_action_execution_markdown,
    summarize_action_execution,
)
from quant_system.portfolio.position_actions import (
    append_position_action_plan_record,
    build_position_action_plan,
    read_position_action_plan_records,
    render_position_action_plan_lines,
)
from quant_system.portfolio.exit_plan import (
    append_exit_plan_record,
    build_exit_plan,
    build_lot_exit_plan,
    read_exit_plan_records,
    render_exit_execution_markdown,
    render_exit_plan_lines,
    render_exit_plan_markdown,
    render_lot_exit_execution_markdown,
    summarize_exit_execution,
    summarize_lot_exit_execution,
)
from quant_system.portfolio.risk_check import check_holding_risk
from quant_system.reports.briefing import BriefingInput, BriefingReport
from quant_system.portfolio.selection_tracker import SelectionRecord, SelectionTracker
from quant_system.reports.daily import DailyReport, DailyReportInput
from quant_system.reports.dragon import DragonValidationInput, DragonValidationReport
from quant_system.reports.discipline_adherence import render_discipline_adherence_markdown
from quant_system.reports.discipline_exceptions import render_discipline_exception_markdown
from quant_system.reports.discipline_summary import render_discipline_summary_lines
from quant_system.reports.experiments import ExperimentReport, build_experiment_summary_payload
from quant_system.reports.weekly import WeeklyReport, WeeklyReportInput
from quant_system.reports.gate_review import render_gate_review_markdown
from quant_system.reports.review_attribution import build_review_attribution_report, render_review_attribution_markdown
from quant_system.reports.review_history import build_review_history, render_review_history_markdown
from quant_system.reports.review_doctor import build_review_doctor_report, render_review_doctor_markdown
from quant_system.reports.final_battle_plan import (
    build_final_battle_plan,
    render_final_battle_plan_markdown,
)
from quant_system.reports.execution_confirm import render_execution_confirmation_markdown
from quant_system.reports.trading_cockpit import build_trading_cockpit, render_trading_cockpit_markdown
from quant_system.reports.trading_day_timeline import build_trading_day_timeline, render_trading_day_timeline_markdown
from quant_system.reports.trading_assistant import build_trading_assistant, render_trading_assistant_markdown
from quant_system.reports.daily_trade_brief import build_daily_trade_brief, render_daily_trade_brief_markdown
from quant_system.reports.strategy_rotation import build_strategy_rotation, render_strategy_rotation_lines
from quant_system.reports.trade_plan_summary import build_trade_plan_summary
from quant_system.reports.rotation_history import (
    read_rotation_snapshots,
    render_rotation_history_card_lines,
    render_rotation_history_lines,
    summarize_rotation_history,
)
from quant_system.reports.pretrade import render_precheck_markdown
from quant_system.reports.premarket import PremarketReport, PremarketReportInput
from quant_system.reports.position_lifecycle import build_position_lifecycle_snapshot, render_position_lifecycle_markdown
from quant_system.risk.pretrade import run_pretrade_check
from quant_system.risk.execution_confirm import (
    append_execution_confirmation_record,
    build_execution_confirmation,
    read_execution_confirmation_records,
)
from quant_system.risk.approval_cooldown import (
    build_approval_cooldown_constraints,
    render_approval_cooldown_markdown,
    summarize_approval_cooldown,
)
from quant_system.risk.attribution_policy import build_attribution_policy, render_attribution_policy_markdown
from quant_system.risk.tradability import build_tradability_check, render_tradability_markdown
from quant_system.risk.sizing import build_allocation_plan
from quant_system.risk.constraint_audit import (
    build_constraint_audit_record,
    persist_constraint_audit,
    read_constraint_audit_records,
    summarize_constraint_audit_records,
)
from quant_system.risk.constraint_policy import apply_constraint_policy_to_health
from quant_system.screening.scoring import score_candidates
from quant_system.strategies.dragon_leader import latest_dragon_diagnostics
from quant_system.strategies.registry import create_strategy, create_strategy_from_config
from quant_system.strategies.portfolio_manager import (
    StrategyPortfolioConfig,
    apply_portfolio_score_adjustment,
    build_strategy_portfolio_plan,
)
from quant_system.storage.jsonl import read_jsonl
from quant_system.storage.frame_cache import write_frame_cache
from quant_system.storage.sqlite_store import SQLiteStore
from quant_system.data.provider_health import ProviderHealthStore

def fetch_akshare_universe_with_retry(attempts: int = 3, retry_sleep: float = 0.5) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(1, max(attempts, 1) + 1):
        try:
            return fetch_akshare_universe()
        except Exception as exc:  # noqa: BLE001 - keep retry/fallback behavior structured.
            last_error = exc
            if attempt < attempts:
                from time import sleep

                sleep(retry_sleep)
    assert last_error is not None
    raise last_error

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quant-system",
        description="A-share quant research, screening, backtesting, and reporting tools",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    screen = subparsers.add_parser("screen", help="Run screening")
    add_dataset_args(screen)
    screen.add_argument("--strategy", default="strong_stock_screen")
    screen.add_argument("--config", type=Path, help="Strategy YAML config")
    screen.add_argument("--portfolio-config", type=Path, help="Dynamic strategy portfolio YAML config")
    screen.add_argument("--settings", type=Path, help="System settings YAML")
    screen.add_argument("--record", action="store_true", help="Record selections")
    screen.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    screen.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    screen.add_argument("--top", type=int, help="Limit to top N results")
    add_strategy_constraint_args(screen)
    add_sector_context_args(screen)

    dragon = subparsers.add_parser("dragon", help="Dragon strategy tools")
    dragon_sub = dragon.add_subparsers(dest="dragon_command", required=True)
    dragon_screen = dragon_sub.add_parser("screen", help="Run dragon screening")
    add_dataset_args(dragon_screen)
    dragon_screen.add_argument("--settings", type=Path, help="System settings YAML")
    dragon_screen.add_argument("--record", action="store_true", help="Record selections")
    dragon_screen.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    dragon_screen.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    dragon_screen.add_argument("--top", type=int, help="Limit to top N results")
    dragon_screen.add_argument("--lookback-days", type=int, help="Limit cached history to recent calendar days before screening")
    dragon_screen.add_argument("--prefilter-symbols", type=int, default=1200, help="Preselect the most active symbols before dragon factor calculation; set 0 to disable")
    add_strategy_constraint_args(dragon_screen)
    add_dragon_gate_arg(dragon_screen)
    add_dragon_entry_model_arg(dragon_screen)
    add_sector_context_args(dragon_screen)
    dragon_check = dragon_sub.add_parser("check", help="Inspect one dragon symbol")
    add_dataset_args(dragon_check)
    dragon_check.add_argument("--symbol", required=True)

    backtest = subparsers.add_parser("backtest", help="Run backtest")
    backtest.add_argument("--csv", type=Path, required=True, help="OHLCV CSV path")
    backtest.add_argument("--strategy", default="trend_breakout")
    backtest.add_argument("--config", type=Path, help="Strategy YAML config")
    backtest.add_argument("--cash", type=float, default=100000)
    backtest.add_argument("--buy-price", choices=["close", "open"], default="open", help="Backtest execution price")
    backtest.add_argument("--execution-timing", choices=["next_bar", "same_bar"], default="next_bar", help="Backtest signal execution timing")
    add_dragon_gate_arg(backtest)
    add_dragon_entry_model_arg(backtest)

    workflow = subparsers.add_parser("workflow", help="Operational workflows")
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_premarket = workflow_sub.add_parser("premarket", help="Run the premarket health and report workflow")
    add_dataset_args(workflow_premarket)
    workflow_premarket.add_argument("--output", type=Path, default=Path("reports/premarket.md"))
    workflow_premarket.add_argument("--summary-output", type=Path, help="Optional JSON workflow summary output")
    workflow_premarket.add_argument("--battle-plan-output", type=Path, help="Optional final battle plan markdown output")
    workflow_premarket.add_argument("--strategy", default="strong_stock_screen")
    workflow_premarket.add_argument("--config", type=Path, help="Strategy YAML config")
    workflow_premarket.add_argument("--portfolio-config", type=Path, help="Dynamic strategy portfolio YAML config")
    workflow_premarket.add_argument("--settings", type=Path, help="System settings YAML")
    workflow_premarket.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    workflow_premarket.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    workflow_premarket.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    workflow_premarket.add_argument("--top", type=int, default=5)
    workflow_premarket.add_argument("--cash", type=float, default=100000)
    workflow_premarket.add_argument("--max-positions", type=int, default=5)
    workflow_premarket.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    workflow_premarket.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    workflow_premarket.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    add_discipline_record_args(workflow_premarket)
    add_approval_cooldown_workflow_args(workflow_premarket)
    workflow_premarket.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    add_sector_context_args(workflow_premarket)
    workflow_premarket.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    workflow_premarket.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    workflow_premarket.add_argument("--max-exposure-pct", type=float, default=0.8)
    workflow_premarket.add_argument("--max-position-pct", type=float, default=0.2)
    workflow_premarket.add_argument("--strict", action="store_true", help="Fail health loading on missing cache entries")
    workflow_premarket.add_argument("--min-rows", type=int, default=30)
    workflow_premarket.add_argument("--max-stale-days", type=int, default=10)
    workflow_premarket.add_argument("--as-of", help="Health check reference date, e.g. 2026-05-29")
    workflow_premarket.add_argument("--refresh-cache", action="store_true", help="Refresh cache before health checks")
    workflow_premarket.add_argument("--refresh-start", help="Refresh start date, e.g. 20240101")
    workflow_premarket.add_argument("--refresh-end", help="Refresh end date; defaults to today")
    workflow_premarket.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"], help="Adjustment mode")
    workflow_premarket.add_argument("--source", default="auto", choices=["auto", "mootdx", "tencent", "akshare", "sina"], help="Data source")
    workflow_premarket.add_argument("--manifest", type=Path, default=Path("data/cache/manifest.jsonl"))
    workflow_premarket.add_argument("--limit", type=int, help="Limit refresh/repair targets")
    workflow_premarket.add_argument("--refresh-stale-days", type=int, help="Refresh cached symbols older than this many calendar days")
    workflow_premarket.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    workflow_premarket.add_argument("--record-actions", action="store_true", help="Persist generated holding action plan")
    workflow_premarket.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    workflow_premarket.add_argument("--record-exit-plan", action="store_true", help="Persist generated exit plan")
    workflow_premarket.add_argument("--target", action="append", default=[], help="Target price, symbol=price")
    workflow_premarket.add_argument("--invalidate", action="append", default=[], help="Invalidated thesis, symbol=reason")
    workflow_premarket.add_argument("--max-holding-days", type=int, default=20)
    workflow_premarket.add_argument("--time-stop-min-return-pct", type=float, default=0.0)
    workflow_premarket.add_argument("--profit-take-pct", type=float, default=0.5)

    workflow_day = workflow_sub.add_parser("trading-day", help="Run the full trading-day report and audit workflow")
    add_dataset_args(workflow_day)
    workflow_day.add_argument("--premarket-output", type=Path, default=Path("reports/premarket.md"))
    workflow_day.add_argument("--battle-plan-output", type=Path, default=Path("reports/final_battle_plan.md"))
    workflow_day.add_argument("--cockpit-output", type=Path, default=Path("reports/trading_cockpit.md"))
    workflow_day.add_argument("--execution-audit-output", type=Path, default=Path("reports/execution_audit.md"))
    workflow_day.add_argument("--lifecycle-output", type=Path, default=Path("reports/lifecycle.md"))
    workflow_day.add_argument("--timeline-output", type=Path, default=Path("reports/trading_timeline.md"))
    workflow_day.add_argument("--assistant-output", type=Path, default=Path("reports/trading_assistant.md"))
    workflow_day.add_argument("--daily-output", type=Path, default=Path("reports/today_trade_brief.md"))
    workflow_day.add_argument("--trade-plan-batch-output", type=Path, default=Path("reports/trade_plan_batch.md"))
    workflow_day.add_argument("--review-doctor-output", type=Path, default=Path("reports/review_doctor.md"))
    workflow_day.add_argument("--review-attribution-output", type=Path, default=Path("reports/review_attribution.md"))
    workflow_day.add_argument("--attribution-policy-output", type=Path, default=Path("reports/attribution_policy.md"))
    workflow_day.add_argument("--summary-output", type=Path, default=Path("reports/trading_day_workflow.json"))
    workflow_day.add_argument("--strategy", default="strong_stock_screen")
    workflow_day.add_argument("--config", type=Path, help="Strategy YAML config")
    workflow_day.add_argument("--portfolio-config", type=Path, help="Dynamic strategy portfolio YAML config")
    workflow_day.add_argument("--settings", type=Path, help="System settings YAML")
    workflow_day.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    workflow_day.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    workflow_day.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    workflow_day.add_argument("--top", type=int, default=5)
    workflow_day.add_argument("--cash", type=float, default=100000)
    workflow_day.add_argument("--max-positions", type=int, default=5)
    workflow_day.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    workflow_day.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    workflow_day.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    add_discipline_record_args(workflow_day)
    add_trading_day_state_args(workflow_day)
    add_approval_cooldown_workflow_args(workflow_day)
    workflow_day.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    add_sector_context_args(workflow_day)
    workflow_day.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    workflow_day.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    workflow_day.add_argument("--max-exposure-pct", type=float, default=0.8)
    workflow_day.add_argument("--max-position-pct", type=float, default=0.2)
    workflow_day.add_argument("--strict", action="store_true", help="Fail health loading on missing cache entries")
    workflow_day.add_argument("--min-rows", type=int, default=30)
    workflow_day.add_argument("--max-stale-days", type=int, default=10)
    workflow_day.add_argument("--as-of", help="Health check reference date, e.g. 2026-05-29")
    workflow_day.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    workflow_day.add_argument("--record-actions", action="store_true", help="Persist generated holding action plan")
    workflow_day.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    workflow_day.add_argument("--record-exit-plan", action="store_true", help="Persist generated exit plan")
    workflow_day.add_argument("--target", action="append", default=[], help="Target price, symbol=price")
    workflow_day.add_argument("--invalidate", action="append", default=[], help="Invalidated thesis, symbol=reason")
    workflow_day.add_argument("--max-holding-days", type=int, default=20)
    workflow_day.add_argument("--time-stop-min-return-pct", type=float, default=0.0)
    workflow_day.add_argument("--profit-take-pct", type=float, default=0.5)
    workflow_day.add_argument("--confirm-log", type=Path, default=Path("data/review/execution_confirms.jsonl"))
    workflow_day.add_argument("--trade-plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    workflow_day.add_argument("--record-trade-plans", action="store_true", help="Persist generated trade-plan batch with duplicate suppression")
    workflow_day.add_argument("--lookahead-days", type=int, default=1)
    workflow_day.add_argument("--repeat-threshold", type=int, default=2)
    workflow_day.add_argument("--stale-days", type=int, default=1)
    workflow_day.add_argument("--record-attribution-policy", action="store_true", help="Persist attribution-derived constraints and discipline record")
    workflow_day.add_argument("--attribution-policy-date", default="", help="Next-session date for attribution-derived constraints")

    workflow_daily = workflow_sub.add_parser("daily", parents=[workflow_day], add_help=False, help="Shortcut for the full daily trading workflow")

    report = subparsers.add_parser("report", help="Generate reports")
    report_sub = report.add_subparsers(dest="report_command", required=True)
    daily = report_sub.add_parser("daily", help="Generate daily markdown report")
    daily.add_argument("--output", type=Path, default=Path("reports/daily.md"))
    add_dataset_args(daily)
    daily.add_argument("--strategy", default="strong_stock_screen")
    daily.add_argument("--config", type=Path, help="Strategy YAML config")
    daily.add_argument("--portfolio-config", type=Path, help="Dynamic strategy portfolio YAML config")
    daily.add_argument("--settings", type=Path, help="System settings YAML")
    daily.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    daily.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    daily.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    daily.add_argument("--top", type=int, help="Keep top N results in the report")
    daily.add_argument("--cash", type=float, default=100000, help="Account cash for position sizing")
    daily.add_argument("--max-positions", type=int, default=5, help="Max positions for sizing")
    daily.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    daily.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    daily.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    add_discipline_record_args(daily)
    daily.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    daily.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    daily.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    add_sector_context_args(daily)

    weekly = report_sub.add_parser("weekly", help="Generate weekly markdown report")
    weekly.add_argument("--output", type=Path, default=Path("reports/weekly.md"))
    weekly.add_argument("--csv", type=Path, help="Optional OHLCV CSV for market temperature and validation")
    weekly.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    weekly.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    weekly.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    weekly.add_argument("--horizons", default="1,3,5")
    weekly.add_argument("--strategy", default="strong_stock_screen")
    weekly.add_argument("--config", type=Path, help="Strategy YAML config")
    weekly.add_argument("--portfolio-config", type=Path, help="Dynamic strategy portfolio YAML config")
    weekly.add_argument("--settings", type=Path, help="System settings YAML")
    weekly.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    weekly.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    weekly.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    add_discipline_record_args(weekly)
    weekly.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    weekly.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    weekly.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    weekly.add_argument("--note", action="append", default=[], help="Weekly notes, repeatable")

    briefing = report_sub.add_parser("briefing", help="Generate trading briefing")
    briefing.add_argument("--output", type=Path, default=Path("reports/briefing.md"))
    add_dataset_args(briefing)
    briefing.add_argument("--strategy", default="strong_stock_screen")
    briefing.add_argument("--config", type=Path, help="Strategy YAML config")
    briefing.add_argument("--settings", type=Path, help="System settings YAML")
    briefing.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    briefing.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    briefing.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    briefing.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    briefing.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    add_discipline_record_args(briefing)
    briefing.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    briefing.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    briefing.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    briefing.add_argument("--cash", type=float, default=100000)
    briefing.add_argument("--top", type=int, default=5)
    add_sector_context_args(briefing)
    briefing.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    briefing.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    briefing.add_argument("--target", action="append", default=[], help="Target price, symbol=price")
    briefing.add_argument("--invalidate", action="append", default=[], help="Invalidated thesis, symbol=reason")
    briefing.add_argument("--max-exposure-pct", type=float, default=0.8)
    briefing.add_argument("--max-position-pct", type=float, default=0.2)
    briefing.add_argument("--max-holding-days", type=int, default=20)
    briefing.add_argument("--time-stop-min-return-pct", type=float, default=0.0)
    briefing.add_argument("--profit-take-pct", type=float, default=0.5)

    premarket = report_sub.add_parser("premarket", help="Generate premarket trading report")
    premarket.add_argument("--output", type=Path, default=Path("reports/premarket.md"))
    add_dataset_args(premarket)
    premarket.add_argument("--strategy", default="strong_stock_screen")
    premarket.add_argument("--config", type=Path, help="Strategy YAML config")
    premarket.add_argument("--settings", type=Path, help="System settings YAML")
    premarket.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    premarket.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    premarket.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    premarket.add_argument("--top", type=int, default=5)
    premarket.add_argument("--cash", type=float, default=100000)
    premarket.add_argument("--max-positions", type=int, default=5)
    premarket.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    premarket.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    premarket.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    add_discipline_record_args(premarket)
    premarket.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    premarket.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    premarket.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    add_sector_context_args(premarket)
    premarket.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    premarket.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    premarket.add_argument("--target", action="append", default=[], help="Target price, symbol=price")
    premarket.add_argument("--invalidate", action="append", default=[], help="Invalidated thesis, symbol=reason")
    premarket.add_argument("--max-exposure-pct", type=float, default=0.8)
    premarket.add_argument("--max-position-pct", type=float, default=0.2)
    premarket.add_argument("--max-holding-days", type=int, default=20)
    premarket.add_argument("--time-stop-min-return-pct", type=float, default=0.0)
    premarket.add_argument("--profit-take-pct", type=float, default=0.5)

    battle_plan = report_sub.add_parser("battle-plan", help="Generate final pretrade battle plan")
    battle_plan.add_argument("--output", type=Path, default=Path("reports/final_battle_plan.md"))
    battle_plan.add_argument("--format", choices=["markdown", "json"], default="markdown")
    add_dataset_args(battle_plan)
    battle_plan.add_argument("--strategy", default="strong_stock_screen")
    battle_plan.add_argument("--config", type=Path, help="Strategy YAML config")
    battle_plan.add_argument("--settings", type=Path, help="System settings YAML")
    battle_plan.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    battle_plan.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    battle_plan.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    battle_plan.add_argument("--top", type=int, default=5)
    battle_plan.add_argument("--cash", type=float, default=100000)
    battle_plan.add_argument("--max-positions", type=int, default=5)
    battle_plan.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    battle_plan.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    battle_plan.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    add_discipline_record_args(battle_plan)
    battle_plan.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    battle_plan.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    battle_plan.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    add_sector_context_args(battle_plan)
    battle_plan.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    battle_plan.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    battle_plan.add_argument("--target", action="append", default=[], help="Target price, symbol=price")
    battle_plan.add_argument("--invalidate", action="append", default=[], help="Invalidated thesis, symbol=reason")
    battle_plan.add_argument("--max-exposure-pct", type=float, default=0.8)
    battle_plan.add_argument("--max-position-pct", type=float, default=0.2)
    battle_plan.add_argument("--max-holding-days", type=int, default=20)
    battle_plan.add_argument("--time-stop-min-return-pct", type=float, default=0.0)
    battle_plan.add_argument("--profit-take-pct", type=float, default=0.5)

    cockpit = report_sub.add_parser("cockpit", help="Generate a unified live trading cockpit")
    cockpit.add_argument("--output", type=Path, default=Path("reports/trading_cockpit.md"))
    cockpit.add_argument("--format", choices=["markdown", "json"], default="markdown")
    add_dataset_args(cockpit)
    cockpit.add_argument("--strategy", default="strong_stock_screen")
    cockpit.add_argument("--config", type=Path, help="Strategy YAML config")
    cockpit.add_argument("--settings", type=Path, help="System settings YAML")
    cockpit.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    cockpit.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    cockpit.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    cockpit.add_argument("--top", type=int, default=5)
    cockpit.add_argument("--cash", type=float, default=100000)
    cockpit.add_argument("--max-positions", type=int, default=5)
    cockpit.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    cockpit.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    cockpit.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    cockpit.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    cockpit.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    cockpit.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    cockpit.add_argument("--confirm-log", type=Path, default=Path("data/review/execution_confirms.jsonl"))
    add_sector_context_args(cockpit)
    cockpit.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    cockpit.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    cockpit.add_argument("--target", action="append", default=[], help="Target price, symbol=price")
    cockpit.add_argument("--invalidate", action="append", default=[], help="Invalidated thesis, symbol=reason")
    cockpit.add_argument("--max-exposure-pct", type=float, default=0.8)
    cockpit.add_argument("--max-position-pct", type=float, default=0.2)
    cockpit.add_argument("--max-holding-days", type=int, default=20)
    cockpit.add_argument("--time-stop-min-return-pct", type=float, default=0.0)
    cockpit.add_argument("--profit-take-pct", type=float, default=0.5)
    cockpit.add_argument("--lookahead-days", type=int, default=1)

    timeline = report_sub.add_parser("timeline", help="Generate trading-day phase reminders")
    timeline.add_argument("--output", type=Path, default=Path("reports/trading_timeline.md"))
    timeline.add_argument("--format", choices=["markdown", "json"], default="markdown")
    add_dataset_args(timeline)
    timeline.add_argument("--strategy", default="strong_stock_screen")
    timeline.add_argument("--config", type=Path, help="Strategy YAML config")
    timeline.add_argument("--settings", type=Path, help="System settings YAML")
    timeline.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    timeline.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    timeline.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    timeline.add_argument("--top", type=int, default=5)
    timeline.add_argument("--cash", type=float, default=100000)
    timeline.add_argument("--max-positions", type=int, default=5)
    timeline.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    timeline.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    timeline.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    timeline.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    timeline.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    timeline.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    timeline.add_argument("--confirm-log", type=Path, default=Path("data/review/execution_confirms.jsonl"))
    add_sector_context_args(timeline)
    timeline.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    timeline.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    timeline.add_argument("--target", action="append", default=[], help="Target price, symbol=price")
    timeline.add_argument("--invalidate", action="append", default=[], help="Invalidated thesis, symbol=reason")
    timeline.add_argument("--max-exposure-pct", type=float, default=0.8)
    timeline.add_argument("--max-position-pct", type=float, default=0.2)
    timeline.add_argument("--max-holding-days", type=int, default=20)
    timeline.add_argument("--time-stop-min-return-pct", type=float, default=0.0)
    timeline.add_argument("--profit-take-pct", type=float, default=0.5)
    timeline.add_argument("--lookahead-days", type=int, default=1)
    timeline.add_argument("--as-of", help="Optional current timestamp/date for phase reminders")
    add_trading_day_state_args(timeline)

    assistant = report_sub.add_parser("assistant", help="Generate one-page trading assistant panel")
    assistant.add_argument("--output", type=Path, default=Path("reports/trading_assistant.md"))
    assistant.add_argument("--format", choices=["markdown", "json"], default="markdown")
    add_dataset_args(assistant)
    assistant.add_argument("--strategy", default="strong_stock_screen")
    assistant.add_argument("--config", type=Path, help="Strategy YAML config")
    assistant.add_argument("--settings", type=Path, help="System settings YAML")
    assistant.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    assistant.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    assistant.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    assistant.add_argument("--top", type=int, default=5)
    assistant.add_argument("--cash", type=float, default=100000)
    assistant.add_argument("--max-positions", type=int, default=5)
    assistant.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    assistant.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    assistant.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    assistant.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    assistant.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    assistant.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    assistant.add_argument("--confirm-log", type=Path, default=Path("data/review/execution_confirms.jsonl"))
    assistant.add_argument("--trade-plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    add_sector_context_args(assistant)
    assistant.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    assistant.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    assistant.add_argument("--target", action="append", default=[], help="Target price, symbol=price")
    assistant.add_argument("--invalidate", action="append", default=[], help="Invalidated thesis, symbol=reason")
    assistant.add_argument("--max-exposure-pct", type=float, default=0.8)
    assistant.add_argument("--max-position-pct", type=float, default=0.2)
    assistant.add_argument("--max-holding-days", type=int, default=20)
    assistant.add_argument("--time-stop-min-return-pct", type=float, default=0.0)
    assistant.add_argument("--profit-take-pct", type=float, default=0.5)
    assistant.add_argument("--lookahead-days", type=int, default=1)
    assistant.add_argument("--as-of", help="Optional current timestamp/date for assistant")
    assistant.add_argument("--repeat-threshold", type=int, default=2)
    assistant.add_argument("--stale-days", type=int, default=1)
    add_trading_day_state_args(assistant)

    dragon_report = report_sub.add_parser("dragon", help="Generate dragon validation report")
    dragon_report.add_argument("--output", type=Path, default=Path("reports/dragon_validation.md"))
    add_dataset_args(dragon_report)
    dragon_report.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    dragon_report.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    dragon_report.add_argument("--horizons", default="1,3,5")
    dragon_report.add_argument("--cash", type=float, default=100000)
    dragon_report.add_argument("--buy-price", choices=["close", "open"], default="open", help="Backtest execution price")
    dragon_report.add_argument("--execution-timing", choices=["next_bar", "same_bar"], default="next_bar", help="Backtest signal execution timing")
    dragon_report.add_argument("--top", type=int, default=10, help="Limit current dragon candidates shown in the report")
    dragon_report.add_argument("--lookback-days", type=int, help="Limit cached history to recent calendar days before dragon validation")
    dragon_report.add_argument("--prefilter-symbols", type=int, default=1200, help="Preselect the most active symbols before dragon factor calculation; set 0 to disable")
    add_dragon_gate_arg(dragon_report)
    add_dragon_entry_model_arg(dragon_report)
    add_sector_context_args(dragon_report)

    data = subparsers.add_parser("data", help="Market data tools")
    data_sub = data.add_subparsers(dest="data_command", required=True)
    fetch_daily = data_sub.add_parser("fetch-daily", help="Fetch A-share daily bars into cache")
    fetch_daily.add_argument("--symbol", required=True, help="Stock symbol, e.g. 000001")
    fetch_daily.add_argument("--start", required=True, help="Start date, e.g. 20240101")
    fetch_daily.add_argument("--end", required=True, help="End date, e.g. 20240527")
    fetch_daily.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"], help="Adjustment mode")
    fetch_daily.add_argument("--cache-dir", type=Path, default=Path("data/cache/daily"))
    fetch_daily.add_argument("--source", default="auto", choices=["auto", "mootdx", "tencent", "akshare", "sina"], help="Data source")

    fetch_batch = data_sub.add_parser("fetch-batch", help="Refresh daily cache for a universe")
    fetch_batch.add_argument("--universe", type=Path, required=True, help="Universe CSV with symbol/name")
    fetch_batch.add_argument("--start", required=True, help="Start date, e.g. 20240101")
    fetch_batch.add_argument("--end", help="End date, e.g. 20240527; defaults to today")
    fetch_batch.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"], help="Adjustment mode")
    fetch_batch.add_argument("--cache-dir", type=Path, default=Path("data/cache/daily"))
    fetch_batch.add_argument("--manifest", type=Path, default=Path("data/cache/manifest.jsonl"))
    fetch_batch.add_argument("--source", default="auto", choices=["auto", "mootdx", "tencent", "akshare", "sina"], help="Data source")
    fetch_batch.add_argument("--limit", type=int, help="Limit the number of symbols")
    fetch_batch.add_argument("--refresh", action="store_true", help="Force refresh even when cached")
    fetch_batch.add_argument("--refresh-stale-days", type=int, help="Refresh cached symbols older than this many calendar days")

    health = data_sub.add_parser("health", help="Check OHLCV data health")
    add_dataset_args(health)
    health.add_argument("--strict", action="store_true", help="Fail on any missing cache entry")
    health.add_argument("--min-rows", type=int, default=30, help="Minimum history rows per symbol")
    health.add_argument("--max-stale-days", type=int, help="Maximum allowed stale days")
    health.add_argument("--as-of", help="Health check reference date, e.g. 2026-05-28")

    repair_plan = data_sub.add_parser("repair-plan", help="Build an OHLCV cache repair plan")
    add_dataset_args(repair_plan)
    repair_plan.add_argument("--strict", action="store_true", help="Fail on any missing cache entry")
    repair_plan.add_argument("--min-rows", type=int, default=30, help="Minimum history rows per symbol")
    repair_plan.add_argument("--max-stale-days", type=int, default=10, help="Maximum allowed stale days")
    repair_plan.add_argument("--as-of", help="Repair plan reference date, e.g. 2026-05-28")

    repair_execute = data_sub.add_parser("repair-execute", help="Execute an OHLCV cache repair plan")
    add_dataset_args(repair_execute)
    repair_execute.add_argument("--strict", action="store_true", help="Fail on any missing cache entry")
    repair_execute.add_argument("--min-rows", type=int, default=30, help="Minimum history rows per symbol")
    repair_execute.add_argument("--max-stale-days", type=int, default=10, help="Maximum allowed stale days")
    repair_execute.add_argument("--as-of", help="Repair plan reference date, e.g. 2026-05-28")
    repair_execute.add_argument("--start", help="Optional override for fetch start date")
    repair_execute.add_argument("--end", help="Optional override for fetch end date")
    repair_execute.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"], help="Adjustment mode")
    repair_execute.add_argument("--source", default="auto", choices=["auto", "mootdx", "tencent", "akshare", "sina"], help="Data source")
    repair_execute.add_argument("--limit", type=int, help="Limit repair targets")
    repair_execute.add_argument("--execute", action="store_true", help="Actually fetch and write cache; default is dry-run")

    universe = data_sub.add_parser("universe", help="Build an A-share universe")
    universe.add_argument("--input", type=Path, help="Optional input CSV to filter")
    universe.add_argument("--output", type=Path, default=Path("configs/universe_a_share.csv"))
    universe.add_argument("--source", default="auto", choices=["auto", "akshare"])
    universe.add_argument("--include-st", action="store_true")
    universe.add_argument("--include-bj", action="store_true")
    universe.add_argument("--exclude-star", action="store_true")
    universe.add_argument("--exclude-chinext", action="store_true")
    universe.add_argument("--min-list-days", type=int)

    db = data_sub.add_parser("db", help="Local SQLite store")
    db.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_sub = db.add_subparsers(dest="db_command", required=True)

    db_init = db_sub.add_parser("init", help="Initialize the SQLite database")
    db_init.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))

    db_import_universe = db_sub.add_parser("import-universe", help="Import a universe into SQLite")
    db_import_universe.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_import_universe.add_argument("--input", type=Path, help="Universe CSV path")
    db_import_universe.add_argument("--source", default="auto", choices=["auto", "akshare"])
    db_import_universe.add_argument("--include-st", action="store_true")
    db_import_universe.add_argument("--include-bj", action="store_true")
    db_import_universe.add_argument("--exclude-star", action="store_true")
    db_import_universe.add_argument("--exclude-chinext", action="store_true")
    db_import_universe.add_argument("--min-list-days", type=int)

    db_import_daily = db_sub.add_parser("import-daily", help="Import one symbol's daily bars")
    db_import_daily.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_import_daily.add_argument("--symbol", required=True)
    db_import_daily.add_argument("--start", required=True)
    db_import_daily.add_argument("--end", required=True)
    db_import_daily.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"])
    db_import_daily.add_argument("--source", default="akshare", choices=["auto", "mootdx", "tencent", "akshare", "sina"])

    db_import_batch_daily = db_sub.add_parser("import-batch-daily", help="Import daily bars for a universe into SQLite")
    db_import_batch_daily.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_import_batch_daily.add_argument("--universe", type=Path, help="Universe CSV path; defaults to SQLite universe table")
    db_import_batch_daily.add_argument("--start", required=True)
    db_import_batch_daily.add_argument("--end", required=True)
    db_import_batch_daily.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"])
    db_import_batch_daily.add_argument("--source", default="auto", choices=["auto", "mootdx", "tencent", "akshare", "sina"])
    db_import_batch_daily.add_argument("--limit", type=int, help="Limit the number of symbols")
    db_import_batch_daily.add_argument("--workers", type=int, default=8, help="Parallel fetch workers")
    db_import_batch_daily.add_argument("--progress-every", type=int, default=100, help="Print progress every N symbols")
    db_import_batch_daily.add_argument("--refresh", action="store_true", help="Refetch symbols even when SQLite already covers the requested date range")
    db_import_batch_daily.add_argument("--include-st", action="store_true", help="When auto-building universe, include ST stocks")
    db_import_batch_daily.add_argument("--include-bj", action="store_true", help="When auto-building universe, include Beijing Stock Exchange stocks")

    db_import_adjustment = db_sub.add_parser("import-adjustment", help="Import one symbol's adjustment factors")
    db_import_adjustment.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_import_adjustment.add_argument("--symbol", required=True)
    db_import_adjustment.add_argument("--start", required=True)
    db_import_adjustment.add_argument("--end", required=True)
    db_import_adjustment.add_argument("--adjust", default="qfq", choices=["qfq", "hfq"])

    db_import_batch_adjustment = db_sub.add_parser("import-batch-adjustment", help="Import adjustment factors for a universe")
    db_import_batch_adjustment.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_import_batch_adjustment.add_argument("--universe", type=Path, help="Universe CSV path; defaults to SQLite universe table")
    db_import_batch_adjustment.add_argument("--start", required=True)
    db_import_batch_adjustment.add_argument("--end", required=True)
    db_import_batch_adjustment.add_argument("--adjust", default="qfq", choices=["qfq", "hfq"])
    db_import_batch_adjustment.add_argument("--limit", type=int, help="Limit the number of symbols")
    db_import_batch_adjustment.add_argument("--workers", type=int, default=4, help="Parallel fetch workers")
    db_import_batch_adjustment.add_argument("--progress-every", type=int, default=100, help="Print progress every N symbols")
    db_import_batch_adjustment.add_argument("--refresh", action="store_true", help="Refetch symbols even when factors already exist")
    db_import_batch_adjustment.add_argument("--include-st", action="store_true", help="When auto-building universe, include ST stocks")
    db_import_batch_adjustment.add_argument("--include-bj", action="store_true", help="When auto-building universe, include Beijing Stock Exchange stocks")

    db_import_minute = db_sub.add_parser("import-minute", help="Fetch minute bars into local Parquet cache and SQLite catalog")
    db_import_minute.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_import_minute.add_argument("--symbol", required=True)
    db_import_minute.add_argument("--start", required=True, help="Start datetime, e.g. 2025-01-02 09:30:00")
    db_import_minute.add_argument("--end", required=True, help="End datetime, e.g. 2025-01-02 15:00:00")
    db_import_minute.add_argument("--period", default="1", choices=["1", "5", "15", "30", "60"])
    db_import_minute.add_argument("--adjust", default="", choices=["", "qfq", "hfq"])
    db_import_minute.add_argument("--source", default="auto", choices=["auto", "akshare-minute", "tencent-minute"])
    db_import_minute.add_argument("--cache-dir", type=Path, default=Path("data/cache/minute"))

    db_import_batch_minute = db_sub.add_parser("import-batch-minute", help="Fetch minute bars for a universe into local cache and SQLite catalog")
    db_import_batch_minute.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_import_batch_minute.add_argument("--universe", type=Path, help="Universe CSV path; defaults to SQLite universe table")
    db_import_batch_minute.add_argument("--start", required=True, help="Start datetime, e.g. 2026-05-25 09:30:00")
    db_import_batch_minute.add_argument("--end", required=True, help="End datetime, e.g. 2026-05-29 15:00:00")
    db_import_batch_minute.add_argument("--period", default="1", choices=["1", "5", "15", "30", "60"])
    db_import_batch_minute.add_argument("--adjust", default="", choices=["", "qfq", "hfq"])
    db_import_batch_minute.add_argument("--source", default="auto", choices=["auto", "akshare-minute", "tencent-minute"])
    db_import_batch_minute.add_argument("--cache-dir", type=Path, default=Path("data/cache/minute"))
    db_import_batch_minute.add_argument("--limit", type=int, help="Limit the number of symbols")
    db_import_batch_minute.add_argument("--workers", type=int, default=2, help="Parallel fetch workers")
    db_import_batch_minute.add_argument("--progress-every", type=int, default=20, help="Print progress every N symbols")
    db_import_batch_minute.add_argument("--refresh", action="store_true", help="Refetch chunks even when catalog already covers them")
    db_import_batch_minute.add_argument("--include-st", action="store_true", help="When auto-building universe, include ST stocks")
    db_import_batch_minute.add_argument("--include-bj", action="store_true", help="When auto-building universe, include Beijing Stock Exchange stocks")

    db_import_review = db_sub.add_parser("import-review", help="Import historical review JSONL logs into SQLite")
    db_import_review.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_import_review.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    db_import_review.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    db_import_review.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"))
    db_import_review.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    db_import_review.add_argument("--discipline-log", type=Path, default=Path("data/review/discipline.jsonl"))
    db_import_review.add_argument("--trade-plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    db_import_review.add_argument("--confirm-log", type=Path, default=Path("data/review/execution_confirms.jsonl"))
    db_import_review.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    db_import_review.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    db_import_review.add_argument("--lifecycle-log", type=Path, default=Path("data/review/lifecycle_snapshots.jsonl"))
    db_import_review.add_argument("--state-log", type=Path, default=Path("data/review/trading_day_states.jsonl"))
    db_import_review.add_argument("--approval-log", type=Path, default=Path("data/review/order_approvals.jsonl"))

    db_screen = db_sub.add_parser("screen", help="Run screening on SQLite data")
    db_screen.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_screen.add_argument("--strategy", default="strong_stock_screen")
    db_screen.add_argument("--config", type=Path, help="Strategy YAML config")
    db_screen.add_argument("--settings", type=Path, help="System settings YAML")
    db_screen.add_argument("--top", type=int, help="Limit to top N results")
    add_strategy_constraint_args(db_screen)
    add_sector_context_args(db_screen)
    add_dragon_gate_arg(db_screen)
    add_dragon_entry_model_arg(db_screen)

    db_health = db_sub.add_parser("health", help="Check SQLite daily bars health")
    db_health.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_health.add_argument("--min-rows", type=int, default=30)
    db_health.add_argument("--max-stale-days", type=int)
    db_health.add_argument("--as-of", help="Health check reference date, e.g. 2026-05-28")
    db_doctor = db_sub.add_parser("doctor", help="Check review-ledger completeness in SQLite")
    db_doctor.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_doctor.add_argument("--format", choices=["json", "markdown"], default="json")
    db_doctor.add_argument("--output", type=Path, help="Optional output path")
    db_catalog = db_sub.add_parser("catalog", help="Show market-data coverage in SQLite and minute cache catalog")
    db_catalog.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_catalog.add_argument("--format", choices=["json", "markdown"], default="json")
    db_sources = db_sub.add_parser("sources", help="Show configured data sources")
    db_sources.add_argument("--settings", type=Path, help="System settings YAML")

    table = data_sub.add_parser("table", help="Fetch table-style market data")
    table.add_argument("--source", default="auto", choices=["auto", "akshare-concept", "akshare-announcement", "akshare-news", "sina-global", "iwencai"])
    table.add_argument("--query", action="append", default=[], help="Query parameters as key=value")
    provider_health = data_sub.add_parser("provider-health", help="Show provider health scores")

    review = subparsers.add_parser("review", help="Review and validation tools")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    selections = review_sub.add_parser("selections", help="Validate historical selections")
    selections.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    selections.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    selections.add_argument("--csv", type=Path, required=True, help="CSV with future OHLCV")
    selections.add_argument("--horizons", default="1,3,5", help="Validation horizons, e.g. 1,3,5")

    trade_add = review_sub.add_parser("trade-add", help="Record a trade")
    trade_add.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    trade_add.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    trade_add.add_argument("--date", required=True)
    trade_add.add_argument("--symbol", required=True)
    trade_add.add_argument("--side", required=True, choices=["BUY", "SELL", "buy", "sell"])
    trade_add.add_argument("--price", type=float, required=True)
    trade_add.add_argument("--quantity", type=int, required=True)
    trade_add.add_argument("--reason", required=True)
    trade_add.add_argument("--name", default="")
    trade_add.add_argument("--strategy", default="")
    trade_add.add_argument("--market-regime", default="")
    trade_add.add_argument("--planned-pct", type=float, default=0.0)
    trade_add.add_argument("--actual-pct", type=float, default=0.0)
    trade_add.add_argument("--planned-price", type=float)
    trade_add.add_argument("--stop-price", type=float)
    trade_add.add_argument("--target-price", type=float)
    trade_add.add_argument("--tags", default="", help="Comma-separated tags, e.g. momentum,plan")
    trade_add.add_argument("--mistake-type", default="")
    trade_add.add_argument("--review", default="")
    trade_add.add_argument("--workflow-summary", type=Path, help="Premarket workflow JSON summary to attach gate status")
    trade_add.add_argument("--trade-plan", type=Path, help="Trade plan JSON produced by portfolio plan")
    trade_add.add_argument("--execution-confirm", type=Path, help="Execution confirmation JSON produced by portfolio confirm")
    trade_add.add_argument("--order-approval", type=Path, help="Final order approval JSON produced by portfolio approve")
    trade_add.add_argument("--gate-status", choices=["pass", "warn", "block"], default="")
    trade_add.add_argument("--gate-message", default="")
    trade_add.add_argument("--gate-reason", action="append", default=[], help="Gate reason, repeatable")
    trade_add.add_argument("--discipline-exception", action="store_true", help="Mark the trade as a documented exception to discipline rules")
    trade_add.add_argument("--exception-reason", default="", help="Reason for the documented discipline exception")

    trade_list = review_sub.add_parser("trade-list", help="List trade journal")
    trade_list.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    trade_list.add_argument("--sqlite", type=Path, help="Optional SQLite store path")

    trade_stats = review_sub.add_parser("trade-stats", help="Summarize trade journal")
    trade_stats.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    trade_stats.add_argument("--sqlite", type=Path, help="Optional SQLite store path")

    gates = review_sub.add_parser("gates", help="Summarize premarket gate discipline from trades")
    gates.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    gates.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    gates.add_argument("--strategy", default="", help="Optional strategy filter")
    gates.add_argument("--symbol", default="", help="Optional symbol filter")
    gates.add_argument("--limit", type=int, default=20, help="Show at most N recent records")
    gates.add_argument("--format", choices=["json", "markdown"], default="json")
    gates.add_argument("--output", type=Path, help="Optional output path")

    exceptions = review_sub.add_parser("exceptions", help="Summarize documented discipline exceptions from trades")
    exceptions.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    exceptions.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    exceptions.add_argument("--limit", type=int, default=20, help="Show at most N recent records")
    exceptions.add_argument("--format", choices=["json", "markdown"], default="json")
    exceptions.add_argument("--output", type=Path, help="Optional output path")

    trade_plan = review_sub.add_parser("trade-plan", help="Summarize recorded trade plans")
    trade_plan.add_argument("--log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    trade_plan.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    trade_plan.add_argument("--limit", type=int, default=20, help="Show at most N recent records")
    trade_plan.add_argument("--format", choices=["json", "markdown"], default="json")
    trade_plan.add_argument("--output", type=Path, help="Optional output path")

    trade_audit = review_sub.add_parser("trade-audit", help="Compare recorded trade plans with actual trades")
    trade_audit.add_argument("--plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    trade_audit.add_argument("--trade-log", type=Path, default=Path("data/review/trades.jsonl"))
    trade_audit.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    trade_audit.add_argument("--limit", type=int, default=20, help="Show at most N recent records")
    trade_audit.add_argument("--format", choices=["json", "markdown"], default="json")
    trade_audit.add_argument("--output", type=Path, help="Optional output path")

    execution_audit = review_sub.add_parser("execution-audit", help="Audit intraday execution confirmations against actual buy trades")
    execution_audit.add_argument("--confirm-log", type=Path, default=Path("data/review/execution_confirms.jsonl"))
    execution_audit.add_argument("--trade-log", type=Path, default=Path("data/review/trades.jsonl"))
    execution_audit.add_argument("--sqlite", type=Path, help="Optional SQLite store path for confirmations and trades")
    execution_audit.add_argument("--lookahead-days", type=int, default=1)
    execution_audit.add_argument("--limit", type=int, default=20, help="Show at most N recent records")
    execution_audit.add_argument("--format", choices=["json", "markdown"], default="json")
    execution_audit.add_argument("--output", type=Path, help="Optional output path")

    approval_audit = review_sub.add_parser("approval-audit", help="Audit final order approvals against actual BUY trades")
    approval_audit.add_argument("--approval-log", type=Path, default=Path("data/review/order_approvals.jsonl"))
    approval_audit.add_argument("--trade-log", type=Path, default=Path("data/review/trades.jsonl"))
    approval_audit.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    approval_audit.add_argument("--sqlite", type=Path, help="Optional SQLite store path for approvals and trades")
    approval_audit.add_argument("--lookahead-days", type=int, default=1)
    approval_audit.add_argument("--value-tolerance-pct", type=float, default=0.02)
    approval_audit.add_argument("--limit", type=int, default=20, help="Show at most N recent records")
    approval_audit.add_argument("--format", choices=["json", "markdown"], default="json")
    approval_audit.add_argument("--output", type=Path, help="Optional output path")

    approval_cooldown = review_sub.add_parser("approval-cooldown", help="Turn approval audit violations into strategy cooldown constraints")
    approval_cooldown.add_argument("--approval-log", type=Path, default=Path("data/review/order_approvals.jsonl"))
    approval_cooldown.add_argument("--trade-log", type=Path, default=Path("data/review/trades.jsonl"))
    approval_cooldown.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    approval_cooldown.add_argument("--sqlite", type=Path, help="Optional SQLite store path for approvals/trades/constraints")
    approval_cooldown.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    approval_cooldown.add_argument("--lookahead-days", type=int, default=1)
    approval_cooldown.add_argument("--value-tolerance-pct", type=float, default=0.02)
    approval_cooldown.add_argument("--block-threshold", type=int, default=1)
    approval_cooldown.add_argument("--warn-threshold", type=int, default=2)
    approval_cooldown.add_argument("--fallback-threshold", type=int, default=2)
    approval_cooldown.add_argument("--warn-exposure-multiplier", type=float, default=0.5)
    approval_cooldown.add_argument("--limit", type=int, default=20)
    approval_cooldown.add_argument("--record", action="store_true", help="Persist generated cooldown constraints into JSONL and optional SQLite")
    approval_cooldown.add_argument("--format", choices=["json", "markdown"], default="json")
    approval_cooldown.add_argument("--output", type=Path, help="Optional output path")

    review_attribution = review_sub.add_parser("attribution", help="Attribute root causes across plan, execution, approval, and lifecycle reviews")
    review_attribution.add_argument("--trade-log", type=Path, default=Path("data/review/trades.jsonl"))
    review_attribution.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    review_attribution.add_argument("--plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    review_attribution.add_argument("--trade-plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    review_attribution.add_argument("--confirm-log", type=Path, default=Path("data/review/execution_confirms.jsonl"))
    review_attribution.add_argument("--approval-log", type=Path, default=Path("data/review/order_approvals.jsonl"))
    review_attribution.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    review_attribution.add_argument("--lifecycle-log", type=Path, default=Path("data/review/lifecycle_snapshots.jsonl"))
    review_attribution.add_argument("--state-log", type=Path, default=Path("data/review/trading_day_states.jsonl"))
    review_attribution.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    review_attribution.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    review_attribution.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    review_attribution.add_argument("--lookahead-days", type=int, default=1)
    review_attribution.add_argument("--value-tolerance-pct", type=float, default=0.02)
    review_attribution.add_argument("--block-threshold", type=int, default=1)
    review_attribution.add_argument("--warn-threshold", type=int, default=2)
    review_attribution.add_argument("--fallback-threshold", type=int, default=2)
    review_attribution.add_argument("--warn-exposure-multiplier", type=float, default=0.5)
    review_attribution.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    review_attribution.add_argument("--as-of", help="Snapshot date, defaults to today")
    review_attribution.add_argument("--limit", type=int, default=12, help="Show at most N root causes")
    review_attribution.add_argument("--format", choices=["json", "markdown"], default="json")
    review_attribution.add_argument("--output", type=Path, help="Optional output path")

    attribution_policy = review_sub.add_parser("attribution-policy", help="Convert review attribution into next-session constraints and discipline advice")
    attribution_policy.add_argument("--trade-log", type=Path, default=Path("data/review/trades.jsonl"))
    attribution_policy.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    attribution_policy.add_argument("--plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    attribution_policy.add_argument("--trade-plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    attribution_policy.add_argument("--confirm-log", type=Path, default=Path("data/review/execution_confirms.jsonl"))
    attribution_policy.add_argument("--approval-log", type=Path, default=Path("data/review/order_approvals.jsonl"))
    attribution_policy.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    attribution_policy.add_argument("--discipline-log", type=Path, default=Path("data/review/discipline.jsonl"))
    attribution_policy.add_argument("--lifecycle-log", type=Path, default=Path("data/review/lifecycle_snapshots.jsonl"))
    attribution_policy.add_argument("--state-log", type=Path, default=Path("data/review/trading_day_states.jsonl"))
    attribution_policy.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    attribution_policy.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    attribution_policy.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    attribution_policy.add_argument("--lookahead-days", type=int, default=1)
    attribution_policy.add_argument("--value-tolerance-pct", type=float, default=0.02)
    attribution_policy.add_argument("--block-threshold", type=int, default=1)
    attribution_policy.add_argument("--warn-threshold", type=int, default=2)
    attribution_policy.add_argument("--fallback-threshold", type=int, default=2)
    attribution_policy.add_argument("--warn-exposure-multiplier", type=float, default=0.5)
    attribution_policy.add_argument("--default-strategy", default="manual_order")
    attribution_policy.add_argument("--effective-date", default="", help="Next-session date for generated constraints")
    attribution_policy.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    attribution_policy.add_argument("--as-of", help="Snapshot date, defaults to today")
    attribution_policy.add_argument("--limit", type=int, default=12, help="Show at most N root causes")
    attribution_policy.add_argument("--record", action="store_true", help="Persist generated constraints and discipline record")
    attribution_policy.add_argument("--format", choices=["json", "markdown"], default="json")
    attribution_policy.add_argument("--output", type=Path, help="Optional output path")

    action_execution = review_sub.add_parser("action-execution", help="Audit holding action plans against actual trades")
    action_execution.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    action_execution.add_argument("--trade-log", type=Path, default=Path("data/review/trades.jsonl"))
    action_execution.add_argument("--sqlite", type=Path, help="Optional SQLite store path for trades")
    action_execution.add_argument("--lookahead-days", type=int, default=3)
    action_execution.add_argument("--limit", type=int, default=20)
    action_execution.add_argument("--format", choices=["json", "markdown"], default="json")
    action_execution.add_argument("--output", type=Path, help="Optional output path")

    exit_audit = review_sub.add_parser("exit-audit", help="Audit exit plans against actual SELL trades")
    exit_audit.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    exit_audit.add_argument("--trade-log", type=Path, default=Path("data/review/trades.jsonl"))
    exit_audit.add_argument("--sqlite", type=Path, help="Optional SQLite store path for trades")
    exit_audit.add_argument("--lookahead-days", type=int, default=3)
    exit_audit.add_argument("--limit", type=int, default=20)
    exit_audit.add_argument("--format", choices=["json", "markdown"], default="json")
    exit_audit.add_argument("--output", type=Path, help="Optional output path")

    lot_exit_audit = review_sub.add_parser("lot-exit-audit", help="Audit lot-level exit plans against FIFO closed lots")
    lot_exit_audit.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    lot_exit_audit.add_argument("--trade-log", type=Path, default=Path("data/review/trades.jsonl"))
    lot_exit_audit.add_argument("--sqlite", type=Path, help="Optional SQLite store path for trades")
    lot_exit_audit.add_argument("--lookahead-days", type=int, default=3)
    lot_exit_audit.add_argument("--limit", type=int, default=20)
    lot_exit_audit.add_argument("--format", choices=["json", "markdown"], default="json")
    lot_exit_audit.add_argument("--output", type=Path, help="Optional output path")

    lot_stats = review_sub.add_parser("lot-stats", help="Summarize lot-level lifecycle from trade journal")
    lot_stats.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    lot_stats.add_argument("--sqlite", type=Path, help="Optional SQLite store path for trades")
    lot_stats.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    lot_stats.add_argument("--as-of", help="Snapshot date, defaults to today")
    lot_stats.add_argument("--format", choices=["json", "markdown"], default="json")
    lot_stats.add_argument("--output", type=Path, help="Optional output path")

    lifecycle_review = review_sub.add_parser("lifecycle", help="Summarize full position lifecycle and execution closure")
    lifecycle_review.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    lifecycle_review.add_argument("--sqlite", type=Path, help="Optional SQLite store path for trades")
    lifecycle_review.add_argument("--cash", type=float, default=100000)
    lifecycle_review.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    lifecycle_review.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    lifecycle_review.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    lifecycle_review.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    lifecycle_review.add_argument("--trade-plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    lifecycle_review.add_argument("--as-of", help="Snapshot date, defaults to today")
    lifecycle_review.add_argument("--lookahead-days", type=int, default=3)
    lifecycle_review.add_argument("--limit", type=int, default=20)
    lifecycle_review.add_argument("--format", choices=["json", "markdown"], default="json")
    lifecycle_review.add_argument("--output", type=Path, help="Optional output path")
    lifecycle_review.add_argument("--max-probe-pct", type=float, default=0.05)
    lifecycle_review.add_argument("--max-position-pct", type=float, default=0.2)
    lifecycle_review.add_argument("--add-step-pct", type=float, default=0.05)
    lifecycle_review.add_argument("--add-profit-trigger-pct", type=float, default=0.03)
    lifecycle_review.add_argument("--reduce-loss-warning-pct", type=float, default=0.03)
    lifecycle_history = review_sub.add_parser("lifecycle-history", help="Summarize persisted review/lifecycle history")
    lifecycle_history.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    lifecycle_history.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    lifecycle_history.add_argument("--trade-plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    lifecycle_history.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    lifecycle_history.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    lifecycle_history.add_argument("--lifecycle-log", type=Path, default=Path("data/review/lifecycle_snapshots.jsonl"))
    lifecycle_history.add_argument("--limit", type=int, default=20)
    lifecycle_history.add_argument("--format", choices=["json", "markdown"], default="json")
    lifecycle_history.add_argument("--output", type=Path, help="Optional output path")
    timeline_history = review_sub.add_parser("timeline-history", help="Summarize persisted trading-day phase states")
    timeline_history.add_argument("--state-log", type=Path, default=Path("data/review/trading_day_states.jsonl"))
    timeline_history.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    timeline_history.add_argument("--limit", type=int, default=20)
    timeline_history.add_argument("--format", choices=["json", "markdown"], default="json")
    timeline_history.add_argument("--output", type=Path, help="Optional output path")
    timeline_watch = review_sub.add_parser("timeline-watch", help="Watch trading-day state gaps and repeated phase issues")
    timeline_watch.add_argument("--state-log", type=Path, default=Path("data/review/trading_day_states.jsonl"))
    timeline_watch.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    timeline_watch.add_argument("--as-of", help="Reference date, defaults to today")
    timeline_watch.add_argument("--repeat-threshold", type=int, default=2)
    timeline_watch.add_argument("--stale-days", type=int, default=1)
    timeline_watch.add_argument("--limit", type=int, default=20)
    timeline_watch.add_argument("--format", choices=["json", "markdown"], default="json")
    timeline_watch.add_argument("--output", type=Path, help="Optional output path")
    review_doctor = review_sub.add_parser("doctor", help="Check review-ledger completeness across JSONL or SQLite")
    review_doctor.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    review_doctor.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    review_doctor.add_argument("--trade-plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    review_doctor.add_argument("--confirm-log", type=Path, default=Path("data/review/execution_confirms.jsonl"))
    review_doctor.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    review_doctor.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    review_doctor.add_argument("--lifecycle-log", type=Path, default=Path("data/review/lifecycle_snapshots.jsonl"))
    review_doctor.add_argument("--state-log", type=Path, default=Path("data/review/trading_day_states.jsonl"))
    review_doctor.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    review_doctor.add_argument("--format", choices=["json", "markdown"], default="json")
    review_doctor.add_argument("--output", type=Path, help="Optional output path")

    approvals = review_sub.add_parser("approvals", help="Summarize persisted final order approvals")
    approvals.add_argument("--log", type=Path, default=Path("data/review/order_approvals.jsonl"))
    approvals.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    approvals.add_argument("--limit", type=int, default=20)
    approvals.add_argument("--symbol", default="", help="Optional symbol filter")
    approvals.add_argument("--status", default="", choices=["", "pass", "warn", "block"], help="Optional status filter")
    approvals.add_argument("--format", choices=["json", "markdown"], default="json")
    approvals.add_argument("--output", type=Path, help="Optional output path")

    promotions = review_sub.add_parser("promotions", help="Summarize strategy promotion history")
    promotions.add_argument("--log", type=Path, default=Path("data/review/promotions.jsonl"))
    promotions.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    promotions.add_argument("--limit", type=int, default=20, help="Show at most N records")
    constraints = review_sub.add_parser("constraints", help="Summarize strategy constraint audit history")
    constraints.add_argument("--log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    constraints.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    constraints.add_argument("--limit", type=int, default=20, help="Show at most N records")

    discipline = review_sub.add_parser("discipline", help="Summarize persisted discipline advice")
    discipline.add_argument("--log", type=Path, default=Path("data/review/discipline.jsonl"))
    discipline.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    discipline.add_argument("--limit", type=int, default=20, help="Show at most N records")
    discipline.add_argument("--format", choices=["json", "markdown"], default="json")

    adherence = review_sub.add_parser("discipline-adherence", help="Compare persisted discipline advice with follow-up trades")
    adherence.add_argument("--log", type=Path, default=Path("data/review/discipline.jsonl"))
    adherence.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    adherence.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    adherence.add_argument("--limit", type=int, default=20, help="Show at most N records")
    adherence.add_argument("--lookahead-days", type=int, default=1, help="Calendar-day follow-up window")
    adherence.add_argument("--format", choices=["json", "markdown"], default="json")
    adherence.add_argument("--output", type=Path, help="Optional output path")

    market = subparsers.add_parser("market", help="Market environment tools")
    market_sub = market.add_subparsers(dest="market_command", required=True)
    temperature = market_sub.add_parser("temperature", help="Calculate market temperature")
    add_dataset_args(temperature)
    temperature.add_argument("--strategy", default="strong_stock_screen")
    temperature.add_argument("--config", type=Path, help="Strategy YAML config")
    temperature.add_argument("--settings", type=Path, help="System settings YAML")
    temperature.add_argument("--top", type=int, help="Limit candidates used for temperature calculation")
    add_sector_context_args(temperature)

    sectors = market_sub.add_parser("sectors", help="Calculate sector strength")
    add_dataset_args(sectors)
    sectors.add_argument("--strategy", default="strong_stock_screen")
    sectors.add_argument("--config", type=Path, help="Strategy YAML config")
    sectors.add_argument("--settings", type=Path, help="System settings YAML")
    sectors.add_argument("--sector-column", help="Sector column name, auto-detect sector/industry/board")
    sectors.add_argument("--top", type=int, default=10)

    portfolio = subparsers.add_parser("portfolio", help="Portfolio and position tools")
    portfolio_sub = portfolio.add_subparsers(dest="portfolio_command", required=True)
    allocate = portfolio_sub.add_parser("allocate", help="Build allocation plan from candidates")
    add_dataset_args(allocate)
    allocate.add_argument("--strategy", default="strong_stock_screen")
    allocate.add_argument("--config", type=Path, help="Strategy YAML config")
    allocate.add_argument("--settings", type=Path, help="System settings YAML")
    allocate.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    allocate.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    allocate.add_argument("--cash", type=float, default=100000)
    allocate.add_argument("--top", type=int, default=5)
    add_sector_context_args(allocate)

    precheck = portfolio_sub.add_parser("precheck", help="Pre-trade risk check")
    add_dataset_args(precheck)
    precheck.add_argument("--symbol", required=True)
    precheck.add_argument("--entry-price", type=float, required=True)
    precheck.add_argument("--planned-pct", type=float, required=True)
    precheck.add_argument("--stop-price", type=float)
    precheck.add_argument("--target-price", type=float)
    precheck.add_argument("--strategy", default="strong_stock_screen")
    precheck.add_argument("--config", type=Path, help="Strategy YAML config")
    precheck.add_argument("--settings", type=Path, help="System settings YAML")
    precheck.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    precheck.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    precheck.add_argument("--cash", type=float, default=100000)
    precheck.add_argument("--top", type=int, default=5)
    precheck.add_argument("--format", choices=["json", "markdown"], default="json")
    add_sector_context_args(precheck)

    confirm = portfolio_sub.add_parser("confirm", help="Final intraday buy confirmation before manual order entry")
    add_dataset_args(confirm)
    confirm.add_argument("--symbol", required=True)
    confirm.add_argument("--current-price", type=float, required=True)
    confirm.add_argument("--planned-pct", type=float, required=True)
    confirm.add_argument("--stop-price", type=float)
    confirm.add_argument("--target-price", type=float)
    confirm.add_argument("--reference-price", type=float, help="Optional planned/reference entry price for chase control")
    confirm.add_argument("--battle-plan", type=Path, help="Optional JSON final battle plan generated by report battle-plan --format json")
    confirm.add_argument("--strategy", default="strong_stock_screen")
    confirm.add_argument("--config", type=Path, help="Strategy YAML config")
    confirm.add_argument("--settings", type=Path, help="System settings YAML")
    confirm.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    confirm.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    confirm.add_argument("--cash", type=float, default=100000)
    confirm.add_argument("--top", type=int, default=5)
    confirm.add_argument("--warn-scale", type=float, default=0.5)
    confirm.add_argument("--max-price-deviation-pct", type=float, default=0.015)
    confirm.add_argument("--hard-chase-pct", type=float, default=0.03)
    confirm.add_argument("--lot-size", type=int, default=100)
    confirm.add_argument("--log", type=Path, default=Path("data/review/execution_confirms.jsonl"))
    confirm.add_argument("--record", action="store_true", help="Append the confirmation result to JSONL and optional SQLite for later execution audit")
    confirm.add_argument("--format", choices=["json", "markdown"], default="json")
    confirm.add_argument("--output", type=Path, help="Optional output path")
    add_sector_context_args(confirm)
    tradable = portfolio_sub.add_parser("tradable", help="Hard tradability gate before placing a manual order")
    add_dataset_args(tradable)
    tradable.add_argument("--symbol", required=True)
    tradable.add_argument("--current-price", type=float, required=True)
    tradable.add_argument("--planned-pct", type=float, required=True)
    tradable.add_argument("--stop-price", type=float)
    tradable.add_argument("--target-price", type=float)
    tradable.add_argument("--reference-price", type=float, help="Optional planned/reference entry price for chase control")
    tradable.add_argument("--strategy", default="strong_stock_screen")
    tradable.add_argument("--config", type=Path, help="Strategy YAML config")
    tradable.add_argument("--settings", type=Path, help="System settings YAML")
    tradable.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    tradable.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    tradable.add_argument("--cash", type=float, default=100000)
    tradable.add_argument("--top", type=int, default=5)
    tradable.add_argument("--battle-plan", type=Path, help="Optional JSON final battle plan generated by report battle-plan --format json")
    tradable.add_argument("--execution-confirm", type=Path, help="Optional execution confirmation JSON")
    tradable.add_argument("--pretrade-json", type=Path, help="Optional pretrade result JSON")
    tradable.add_argument("--as-of", help="Reference date, defaults to today")
    tradable.add_argument("--max-stale-days", type=int, default=1)
    tradable.add_argument("--limit-pct", type=float, default=0.10)
    tradable.add_argument("--limit-buffer-pct", type=float, default=0.002)
    tradable.add_argument("--lot-size", type=int, default=100)
    tradable.add_argument("--warn-scale", type=float, default=0.5)
    tradable.add_argument("--max-price-deviation-pct", type=float, default=0.015)
    tradable.add_argument("--hard-chase-pct", type=float, default=0.03)
    tradable.add_argument("--format", choices=["json", "markdown"], default="json")
    tradable.add_argument("--output", type=Path, help="Optional output path")
    add_sector_context_args(tradable)

    approve = portfolio_sub.add_parser("approve", help="Generate final order approval from assistant, battle, pretrade, confirmation, and tradability gates")
    add_dataset_args(approve)
    approve.add_argument("--symbol", required=True)
    approve.add_argument("--current-price", type=float, required=True)
    approve.add_argument("--planned-pct", type=float, required=True)
    approve.add_argument("--stop-price", type=float)
    approve.add_argument("--target-price", type=float)
    approve.add_argument("--reference-price", type=float, help="Optional planned/reference entry price for chase control")
    approve.add_argument("--strategy", default="strong_stock_screen")
    approve.add_argument("--config", type=Path, help="Strategy YAML config")
    approve.add_argument("--settings", type=Path, help="System settings YAML")
    approve.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    approve.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    approve.add_argument("--cash", type=float, default=100000)
    approve.add_argument("--top", type=int, default=5)
    approve.add_argument("--battle-plan", type=Path, help="Optional JSON final battle plan generated by report battle-plan --format json")
    approve.add_argument("--execution-confirm", type=Path, help="Optional execution confirmation JSON")
    approve.add_argument("--pretrade-json", type=Path, help="Optional pretrade result JSON")
    approve.add_argument("--assistant-json", type=Path, help="Optional trading assistant JSON")
    approve.add_argument("--as-of", help="Reference date, defaults to today")
    approve.add_argument("--max-stale-days", type=int, default=1)
    approve.add_argument("--limit-pct", type=float, default=0.10)
    approve.add_argument("--limit-buffer-pct", type=float, default=0.002)
    approve.add_argument("--lot-size", type=int, default=100)
    approve.add_argument("--warn-scale", type=float, default=0.5)
    approve.add_argument("--max-price-deviation-pct", type=float, default=0.015)
    approve.add_argument("--hard-chase-pct", type=float, default=0.03)
    approve.add_argument("--log", type=Path, default=Path("data/review/order_approvals.jsonl"))
    approve.add_argument("--record", action="store_true", help="Append the final approval to JSONL and optional SQLite")
    approve.add_argument("--format", choices=["json", "markdown"], default="json")
    approve.add_argument("--output", type=Path, help="Optional output path")
    add_sector_context_args(approve)

    positions = portfolio_sub.add_parser("positions", help="Rebuild current positions from trade journal")
    positions.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    positions.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    positions.add_argument("--cash", type=float, default=100000)
    positions.add_argument("--price", action="append", default=[], help="Current price, symbol=price")

    lots = portfolio_sub.add_parser("lots", help="Build lot-level position lifecycle")
    lots.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    lots.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    lots.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    lots.add_argument("--as-of", help="Snapshot date, defaults to today")
    lots.add_argument("--format", choices=["json", "markdown"], default="json")
    lots.add_argument("--output", type=Path, help="Optional output path")
    lots.add_argument("--log", type=Path, default=Path("data/review/lot_books.jsonl"))
    lots.add_argument("--record", action="store_true", help="Append the generated lot lifecycle snapshot to JSONL")

    lifecycle = portfolio_sub.add_parser("lifecycle", help="Build a unified position lifecycle snapshot")
    lifecycle.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    lifecycle.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    lifecycle.add_argument("--cash", type=float, default=100000)
    lifecycle.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    lifecycle.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    lifecycle.add_argument("--action-log", type=Path, default=Path("data/review/position_actions.jsonl"))
    lifecycle.add_argument("--exit-log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    lifecycle.add_argument("--trade-plan-log", type=Path, default=Path("data/review/trade_plans.jsonl"))
    lifecycle.add_argument("--as-of", help="Snapshot date, defaults to today")
    lifecycle.add_argument("--lookahead-days", type=int, default=3)
    lifecycle.add_argument("--limit", type=int, default=20)
    lifecycle.add_argument("--format", choices=["json", "markdown"], default="json")
    lifecycle.add_argument("--output", type=Path, help="Optional output path")
    lifecycle.add_argument("--record", action="store_true", help="Persist the lifecycle snapshot to SQLite when --sqlite is set")
    lifecycle.add_argument("--max-probe-pct", type=float, default=0.05)
    lifecycle.add_argument("--max-position-pct", type=float, default=0.2)
    lifecycle.add_argument("--add-step-pct", type=float, default=0.05)
    lifecycle.add_argument("--add-profit-trigger-pct", type=float, default=0.03)
    lifecycle.add_argument("--reduce-loss-warning-pct", type=float, default=0.03)

    plan = portfolio_sub.add_parser("plan", help="Build and optionally persist a trade plan")
    add_dataset_args(plan)
    plan.add_argument("--symbol", required=True)
    plan.add_argument("--entry-price", type=float, required=True)
    plan.add_argument("--planned-pct", type=float, required=True)
    plan.add_argument("--stop-price", type=float)
    plan.add_argument("--target-price", type=float)
    plan.add_argument("--strategy", default="strong_stock_screen")
    plan.add_argument("--config", type=Path, help="Strategy YAML config")
    plan.add_argument("--settings", type=Path, help="System settings YAML")
    plan.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    plan.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    plan.add_argument("--cash", type=float, default=100000)
    plan.add_argument("--top", type=int, default=5)
    plan.add_argument("--trade-date", help="Optional trade date, defaults to today")
    plan.add_argument("--format", choices=["json", "markdown"], default="json")
    plan.add_argument("--output", type=Path, help="Optional output path for the rendered plan")
    plan.add_argument("--log", type=Path, default=Path("data/review/trade_plans.jsonl"), help="Trade plan JSONL log")
    plan.add_argument("--record", action="store_true", help="Append the generated plan to the JSONL log")
    plan.add_argument("--discipline-exception", action="store_true", help="Mark the trade as a documented exception to discipline rules")
    plan.add_argument("--exception-reason", default="", help="Reason for the documented discipline exception")

    plan_batch = portfolio_sub.add_parser("plan-batch", help="Build and optionally persist a batch of trade plans")
    add_dataset_args(plan_batch)
    plan_batch.add_argument("--strategy", default="strong_stock_screen")
    plan_batch.add_argument("--config", type=Path, help="Strategy YAML config")
    plan_batch.add_argument("--settings", type=Path, help="System settings YAML")
    plan_batch.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    plan_batch.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    plan_batch.add_argument("--cash", type=float, default=100000)
    plan_batch.add_argument("--top", type=int, default=5)
    plan_batch.add_argument("--trade-date", help="Optional trade date, defaults to today")
    plan_batch.add_argument("--format", choices=["json", "markdown"], default="json")
    plan_batch.add_argument("--output", type=Path, help="Optional output path for the rendered batch")
    plan_batch.add_argument("--log", type=Path, default=Path("data/review/trade_plans.jsonl"), help="Trade plan JSONL log")
    plan_batch.add_argument("--record", action="store_true", help="Append generated plans to the JSONL log")
    plan_batch.add_argument("--discipline-exception", action="store_true", help="Mark the plans as documented exceptions to discipline rules")
    plan_batch.add_argument("--exception-reason", default="", help="Reason for the documented discipline exception")

    holding_risk = portfolio_sub.add_parser("risk", help="Check holding risk")
    holding_risk.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    holding_risk.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    holding_risk.add_argument("--cash", type=float, default=100000)
    holding_risk.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    holding_risk.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    holding_risk.add_argument("--max-exposure-pct", type=float, default=0.8)
    holding_risk.add_argument("--max-position-pct", type=float, default=0.2)

    position_actions = portfolio_sub.add_parser("actions", help="Build actionable position risk instructions")
    position_actions.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    position_actions.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    position_actions.add_argument("--cash", type=float, default=100000)
    position_actions.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    position_actions.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    position_actions.add_argument("--max-exposure-pct", type=float, default=0.8)
    position_actions.add_argument("--max-position-pct", type=float, default=0.2)
    position_actions.add_argument("--target-exposure-pct", type=float, help="Optional stricter target total exposure")
    position_actions.add_argument("--format", choices=["json", "markdown"], default="json")
    position_actions.add_argument("--output", type=Path, help="Optional output path")
    position_actions.add_argument("--log", type=Path, default=Path("data/review/position_actions.jsonl"))
    position_actions.add_argument("--record", action="store_true", help="Append the generated action plan to the JSONL log")

    exit_plan = portfolio_sub.add_parser("exit-plan", help="Build actionable sell/exit plans for current positions")
    exit_plan.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    exit_plan.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    exit_plan.add_argument("--cash", type=float, default=100000)
    exit_plan.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    exit_plan.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    exit_plan.add_argument("--target", action="append", default=[], help="Target price, symbol=price")
    exit_plan.add_argument("--invalidate", action="append", default=[], help="Invalidated thesis, symbol=reason")
    exit_plan.add_argument("--max-position-pct", type=float, default=0.2)
    exit_plan.add_argument("--max-holding-days", type=int, default=20)
    exit_plan.add_argument("--time-stop-min-return-pct", type=float, default=0.0)
    exit_plan.add_argument("--profit-take-pct", type=float, default=0.5)
    exit_plan.add_argument("--plan-date", help="Optional plan date, defaults to today")
    exit_plan.add_argument("--lot-level", action="store_true", help="Generate one exit plan item per open buy lot")
    exit_plan.add_argument("--format", choices=["json", "markdown"], default="json")
    exit_plan.add_argument("--output", type=Path, help="Optional output path")
    exit_plan.add_argument("--log", type=Path, default=Path("data/review/exit_plans.jsonl"))
    exit_plan.add_argument("--record", action="store_true", help="Append the generated exit plan to the JSONL log")

    optimize = subparsers.add_parser("optimize", help="Strategy experiments and optimization tools")
    optimize_sub = optimize.add_subparsers(dest="optimize_command", required=True)
    experiments = optimize_sub.add_parser("experiments", help="Run parameter experiments")
    experiments.add_argument("--csv", type=Path, required=True, help="OHLCV CSV path")
    experiments.add_argument("--preset", default="strong_stock_basic", help="Built-in experiment preset")
    experiments.add_argument("--cases", type=Path, help="YAML experiment case file")
    experiments.add_argument("--horizons", default="1,3,5", help="Validation horizons, e.g. 1,3,5")
    experiments.add_argument("--top", type=int, default=5)
    experiments.add_argument("--min-history", type=int, default=25)
    experiments.add_argument("--recommend-horizon", type=int, default=3, help="Preferred horizon in recommendations")
    experiments.add_argument("--recommend-min-count", type=int, default=5, help="Minimum samples for recommendation")
    experiments.add_argument("--output", type=Path, help="Optional JSON output path")
    experiments.add_argument("--report-output", type=Path, help="Optional Markdown report path")
    experiments.add_argument("--summary-output", type=Path, help="Optional structured summary JSON path")
    calibration = optimize_sub.add_parser(
        "structure-calibration",
        help="Calibrate structure score, chase risk, candle warning, and false-breakout thresholds",
    )
    calibration.add_argument("--csv", type=Path, required=True, help="OHLCV CSV path")
    calibration.add_argument("--cash", type=float, default=100000)
    calibration.add_argument("--buy-price", choices=["close", "open"], default="open", help="Backtest execution price")
    calibration.add_argument("--execution-timing", choices=["next_bar", "same_bar"], default="next_bar")
    calibration.add_argument("--min-20d-return", type=float, default=0.12)
    calibration.add_argument("--min-volume-ratio", type=float, default=1.5)
    calibration.add_argument("--max-volume-ratio", type=float, default=6.0)
    calibration.add_argument("--max-atr-pct", type=float, default=0.12)
    calibration.add_argument("--min-ma20-slope", type=float, default=0.0)
    calibration.add_argument("--max-close-ma20-gap", type=float, default=0.45)
    calibration.add_argument("--max-rsi", type=float, default=90.0)
    calibration.add_argument("--min-traded-value", type=float, default=0.0)
    calibration.add_argument("--format", choices=["json", "markdown"], default="json")
    calibration.add_argument("--output", type=Path, help="Optional output path")
    reliability = optimize_sub.add_parser("backtest-reliability", help="Audit backtest credibility across strategies, periods, and regimes")
    reliability.add_argument("--csv", type=Path, required=True, help="OHLCV CSV path")
    reliability.add_argument("--strategy", action="append", default=[], help="Built-in strategy name, repeatable")
    reliability.add_argument("--config", action="append", type=Path, default=[], help="Strategy YAML config, repeatable")
    reliability.add_argument("--cash", type=float, default=100000)
    reliability.add_argument("--buy-price", choices=["close", "open"], default="open", help="Backtest execution price")
    reliability.add_argument("--execution-timing", choices=["next_bar", "same_bar"], default="next_bar")
    reliability.add_argument("--train-ratio", type=float, default=0.7)
    reliability.add_argument("--regime-lookback", type=int, default=20)
    reliability.add_argument("--bull-threshold", type=float, default=0.05)
    reliability.add_argument("--bear-threshold", type=float, default=-0.05)
    reliability.add_argument("--min-rows-per-symbol", type=int, default=30)
    reliability.add_argument("--max-stale-days", type=int)
    reliability.add_argument("--as-of", help="Reference date for stale data checks, YYYY-MM-DD")
    reliability.add_argument("--format", choices=["json", "markdown"], default="json")
    reliability.add_argument("--output", type=Path, help="Optional output path")
    portfolio_calibration = optimize_sub.add_parser("portfolio-calibration", help="Calibrate dynamic strategy portfolio budgets and caps")
    portfolio_calibration.add_argument("--csv", type=Path, required=True, help="OHLCV CSV path")
    portfolio_calibration.add_argument("--portfolio-config", type=Path, default=Path("configs/strategy_portfolio.yaml"), help="Strategy portfolio YAML config")
    portfolio_calibration.add_argument("--cash", type=float, default=100000)
    portfolio_calibration.add_argument("--buy-price", choices=["close", "open"], default="open", help="Backtest execution price")
    portfolio_calibration.add_argument("--execution-timing", choices=["next_bar", "same_bar"], default="next_bar")
    portfolio_calibration.add_argument("--rebalance-period", type=int, default=5)
    portfolio_calibration.add_argument("--max-positions", type=int, default=5)
    portfolio_calibration.add_argument("--min-history-days", type=int, default=30)
    portfolio_calibration.add_argument("--train-ratio", type=float, default=0.7)
    portfolio_calibration.add_argument("--preset", choices=["compact", "full"], default="compact")
    portfolio_calibration.add_argument("--format", choices=["json", "markdown"], default="json")
    portfolio_calibration.add_argument("--output", type=Path, help="Optional output path")
    export_strategy = optimize_sub.add_parser("export-strategy", help="Export strategy YAML from experiment summary")
    export_strategy.add_argument("--summary", type=Path, required=True, help="Experiment summary JSON")
    export_strategy.add_argument("--output", type=Path, required=True, help="Strategy YAML output path")
    export_strategy.add_argument("--name", help="Optional strategy name override")
    export_strategy.add_argument("--description", help="Optional strategy description override")
    validate_strategy = optimize_sub.add_parser("validate-strategy", help="Validate one strategy YAML")
    validate_strategy.add_argument("--config", type=Path, required=True, help="Strategy YAML path")
    validate_strategy.add_argument("--csv", type=Path, help="Optional OHLCV CSV for a smoke test")
    validate_strategy.add_argument("--trade-plan-log", type=Path, help="Optional trade plan JSONL log for plan-pressure signals")
    validate_strategies = optimize_sub.add_parser("validate-strategies", help="Validate a directory of strategy YAML files")
    validate_strategies.add_argument("--dir", type=Path, default=Path("configs/strategies"), help="Strategy YAML directory")
    validate_strategies.add_argument("--csv", type=Path, help="Optional OHLCV CSV for a smoke test")
    validate_strategies.add_argument("--trade-plan-log", type=Path, help="Optional trade plan JSONL log for plan-pressure signals")
    promote_strategy = optimize_sub.add_parser("promote-strategy", help="Export a promoted strategy and optionally backtest it")
    promote_strategy.add_argument("--summary", type=Path, required=True, help="Experiment summary JSON")
    promote_strategy.add_argument("--output", type=Path, required=True, help="Strategy YAML output path")
    promote_strategy.add_argument("--name", help="Optional strategy name override")
    promote_strategy.add_argument("--description", help="Optional strategy description override")
    promote_strategy.add_argument("--csv", type=Path, help="Optional OHLCV CSV for a smoke backtest")
    promote_strategy.add_argument("--backtest", action="store_true", help="Run one backtest after promotion")
    promote_strategy.add_argument("--buy-price", choices=["close", "open"], default="open", help="Backtest execution price")
    promote_strategy.add_argument("--execution-timing", choices=["next_bar", "same_bar"], default="next_bar", help="Backtest signal execution timing")
    promote_strategy.add_argument("--cash", type=float, default=100000)
    promote_strategy.add_argument("--promotion-output", type=Path, help="Optional promotion result JSON")
    promote_strategy.add_argument("--promotion-log", type=Path, help="Optional promotion history JSONL")
    promote_strategy.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    promote_strategy.add_argument("--trade-plan-log", type=Path, help="Optional trade plan JSONL log for plan-pressure signals")
    strategy_health = optimize_sub.add_parser("health", help="Summarize strategy health from SQLite")
    strategy_health.add_argument("--sqlite", type=Path, default=Path("data/quant.sqlite"), help="SQLite store path")
    rotation = optimize_sub.add_parser("rotation", help="Rank strategies for rotation from health and constraints")
    rotation.add_argument("--sqlite", type=Path, default=Path("data/quant.sqlite"), help="SQLite store path")
    rotation.add_argument("--settings", type=Path, help="System settings YAML")
    rotation.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    rotation.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    rotation.add_argument("--limit", type=int, default=5)
    rotation.add_argument("--format", choices=["json", "markdown"], default="json")
    rotation.add_argument("--output", type=Path, help="Optional output file for the current rotation result")
    rotation.add_argument("--snapshot-dir", type=Path, help="Optional directory for timestamped rotation snapshots")
    rotation_history = optimize_sub.add_parser("rotation-history", help="Summarize historical rotation snapshots")
    rotation_history.add_argument("--snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
    rotation_history.add_argument("--limit", type=int, default=20)
    rotation_history.add_argument("--format", choices=["json", "markdown"], default="json")
    rotation_history.add_argument("--output", type=Path, help="Optional output file for the history summary")

    return parser


def add_dataset_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--csv", type=Path, help="OHLCV CSV path")
    parser.add_argument("--cache-dir", type=Path, help="Local daily cache directory")
    parser.add_argument("--universe", type=Path, help="Universe CSV used for cached multi-symbol loads")



def add_sector_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sector-column", help="Sector column name, auto-detect sector/industry/board")
    parser.add_argument("--sector-top", type=int, default=5, help="Number of top sectors to consider")
    parser.add_argument("--only-top-sectors", action="store_true", help="Keep only candidates in top sectors")


def add_discipline_record_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--record-discipline", action="store_true", help="Persist discipline advice for review")
    parser.add_argument("--discipline-log", type=Path, default=Path("data/review/discipline.jsonl"))


def add_strategy_constraint_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    parser.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    parser.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    add_approval_cooldown_workflow_args(parser)


def add_trading_day_state_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--record-state", action="store_true", help="Persist trading-day phase state for review")
    parser.add_argument("--state-log", type=Path, default=Path("data/review/trading_day_states.jsonl"))


def add_approval_cooldown_workflow_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--approval-log", type=Path, default=Path("data/review/order_approvals.jsonl"))
    parser.add_argument("--disable-approval-cooldown", action="store_true", help="Do not auto-derive cooldown constraints from approval audit")
    parser.add_argument("--record-approval-cooldown", action="store_true", help="Persist auto-derived approval cooldown constraints")
    parser.add_argument("--approval-lookahead-days", type=int, default=1)
    parser.add_argument("--approval-value-tolerance-pct", type=float, default=0.02)
    parser.add_argument("--approval-block-threshold", type=int, default=1)
    parser.add_argument("--approval-warn-threshold", type=int, default=2)
    parser.add_argument("--approval-fallback-threshold", type=int, default=2)
    parser.add_argument("--approval-warn-exposure-multiplier", type=float, default=0.5)


def add_dragon_gate_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--entry-gate",
        choices=["all", "pass-watch", "pass"],
        default="all",
        help="Filter dragon_leader entries by gate status.",
    )


def add_dragon_entry_model_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dragon-entry-model",
        choices=["signal-day", "next-open"],
        default="signal-day",
        help="dragon_leader only: signal-day buy or next-open buy",
    )
    parser.add_argument("--max-next-open-gap", type=float, default=0.07, help="Max allowed next-open gap")
    parser.add_argument("--min-next-open-gap", type=float, default=-0.03, help="Min allowed next-open gap")
    parser.add_argument("--allow-next-open-below-ma5", action="store_true", help="Allow next-open entry below MA5")

def records_from_selection(strategy_name: str, selection_rows: list[dict]) -> list[SelectionRecord]:
    records: list[SelectionRecord] = []
    for item in selection_rows:
        symbol = str(item.get("symbol", "SINGLE"))
        records.append(
            SelectionRecord(
                date=str(item.get("date", ""))[:10],
                strategy=strategy_name,
                symbol=symbol,
                name=str(item.get("name", "")),
                close=float(item.get("close", 0.0)),
                reason=str(item.get("reason", "")),
                entry_gate=str(item.get("entry_gate", "")),
                dragon_state=str(item.get("dragon_state", "")),
                dragon_tags=str(item.get("dragon_tags", "")),
                dragon_score=float(item.get("dragon_score", 0.0) or 0.0),
                seal_quality_score=float(item.get("seal_quality_score", 0.0) or 0.0),
            )
        )
    return records

def strategy_from_args(args: argparse.Namespace):
    if getattr(args, "config", None):
        return create_strategy_from_config(args.config)
    kwargs = {}
    if getattr(args, "strategy", "") == "dragon_leader" and hasattr(args, "entry_gate"):
        kwargs["entry_gate"] = args.entry_gate
    if getattr(args, "strategy", "") == "dragon_leader" and hasattr(args, "dragon_entry_model"):
        kwargs["entry_model"] = args.dragon_entry_model
        kwargs["max_next_open_gap"] = args.max_next_open_gap
        kwargs["min_next_open_gap"] = args.min_next_open_gap
        kwargs["require_next_open_above_ma5"] = not args.allow_next_open_below_ma5
    return create_strategy(args.strategy, **kwargs)

def settings_from_args(args: argparse.Namespace):
    settings = load_settings(getattr(args, "settings", None))
    strategy = getattr(args, "_resolved_strategy", None)
    override = getattr(strategy, "scoring_weights", None)
    constraint_override = getattr(strategy, "constraint_policy", None)
    if not override and not constraint_override:
        return settings
    merged_scoring = dict(settings.scoring.weights)
    for key, value in dict(override or {}).items():
        merged_scoring[str(key)] = float(value)
    merged_constraint_policy = settings.risk.constraint_policy.to_mapping()
    for key, value in dict(constraint_override or {}).items():
        merged_constraint_policy[str(key)] = value
    return SystemSettings.from_mapping(
        {
            "scoring": {"weights": merged_scoring},
            "risk": {
                "regime_exposure": settings.risk.regime_exposure,
                "cap_by_risk": settings.risk.cap_by_risk,
                "constraint_policy": merged_constraint_policy,
            },
            "data_sources": settings.data_sources.__dict__,
        }
    )


def source_from_args(args: argparse.Namespace, attr: str, default: str = "auto") -> str:
    settings = settings_from_args(args)
    data_sources = getattr(settings, "data_sources", None)
    if data_sources is None:
        return default
    resolved = getattr(data_sources, attr, default)
    return str(resolved or default)


def source_or_default(args: argparse.Namespace, explicit_source: str, attr: str, default: str = "auto") -> str:
    if explicit_source != "auto":
        return explicit_source
    resolved = source_from_args(args, attr, default)
    if resolved.strip().lower() in {"csv", "cache", "local"}:
        return default
    return resolved

def enrich_and_score_candidates(
    frame: pd.DataFrame,
    candidates: pd.DataFrame,
    weights: dict[str, float],
    sector_column: str | None = None,
    sector_top: int = 5,
    only_top_sectors: bool = False,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()

    scored = candidates.copy()
    sectors = calculate_sector_strength(frame, scored, sector_column=sector_column, top=max(sector_top, 1))
    scored = annotate_candidates_with_sector_strength(scored, sectors, sector_column=sector_column)
    if only_top_sectors:
        scored = filter_candidates_by_top_sectors(scored, sectors, top_n=sector_top, sector_column=sector_column)
    if scored.empty:
        return scored
    return score_candidates(scored, weights)


def apply_strategy_gate_to_candidates(candidates: pd.DataFrame, strategy_health: dict | None) -> pd.DataFrame:
    if candidates.empty or not strategy_health:
        return candidates.copy()
    gated = candidates.copy()
    gated["strategy_alert_level"] = str(strategy_health.get("alert_level", "pass") or "pass")
    gated["strategy_action"] = str(strategy_health.get("action", "keep") or "keep")
    gated["strategy_policy_state"] = str(strategy_health.get("policy_state", "") or "")
    gated["strategy_exposure_multiplier"] = _strategy_health_exposure_multiplier(strategy_health)
    gated["strategy_actionable"] = _strategy_health_allows_new_positions(strategy_health)
    gated["strategy_constraint_alerts"] = ",".join(str(item) for item in list(strategy_health.get("alerts") or []))
    note = str(strategy_health.get("policy_note", "") or "")
    if note:
        gated["strategy_constraint_note"] = note
    return gated


def _strategy_health_allows_new_positions(strategy_health: dict | None) -> bool:
    if not strategy_health:
        return True
    alert_level = str(strategy_health.get("alert_level", "pass") or "pass")
    action = str(strategy_health.get("action", "keep") or "keep")
    if alert_level == "block" or action == "pause":
        return False
    return _strategy_health_exposure_multiplier(strategy_health) > 0


def _strategy_health_exposure_multiplier(strategy_health: dict | None) -> float:
    if not strategy_health:
        return 1.0
    value = strategy_health.get("policy_exposure_multiplier")
    if value in (None, ""):
        alert_level = str(strategy_health.get("alert_level", "pass") or "pass")
        action = str(strategy_health.get("action", "keep") or "keep")
        if alert_level == "block" or action == "pause":
            return 0.0
        if alert_level == "warn" or action == "reduce":
            return 0.5
        return 1.0
    return max(0.0, min(float(value), 1.0))


def screened_candidates_from_args(
    args: argparse.Namespace,
    frame: pd.DataFrame,
    *,
    strategy=None,
    settings: SystemSettings | None = None,
    strategy_health: dict | None = None,
    only_top_sectors: bool | None = None,
    top: int | None = None,
    sector_top: int | None = None,
) -> pd.DataFrame:
    settings = settings or settings_from_args(args)
    if getattr(args, "portfolio_config", None):
        portfolio_config = StrategyPortfolioConfig.from_yaml(args.portfolio_config)
        health_by_strategy = {
            str(item.get("strategy", "") or ""): item
            for item in _strategy_health_from_args(args)
            if str(item.get("strategy", "") or "")
        }
        plan = build_strategy_portfolio_plan(
            frame,
            portfolio_config,
            strategy_health_by_name=health_by_strategy,
        )
        candidates = plan.candidates
        candidates = enrich_and_score_candidates(
            frame,
            candidates,
            settings.scoring.weights,
            sector_column=getattr(args, "sector_column", None),
            sector_top=sector_top if sector_top is not None else getattr(args, "sector_top", 5),
            only_top_sectors=only_top_sectors if only_top_sectors is not None else getattr(args, "only_top_sectors", False),
        )
        candidates = apply_portfolio_score_adjustment(candidates)
        candidate_limit = top if top is not None else getattr(args, "top", None)
        if candidate_limit:
            candidates = candidates.head(candidate_limit)
        candidates.attrs["selection_strategy_name"] = portfolio_config.name
        candidates.attrs["strategy_portfolio_plan"] = {
            "name": plan.name,
            "market_temperature": plan.market_temperature.to_dict(),
            "sleeves": [item.to_dict() for item in plan.sleeves],
        }
        args._strategy_portfolio_plan = candidates.attrs["strategy_portfolio_plan"]
        return candidates

    strategy = strategy or strategy_from_args(args)
    args._resolved_strategy = strategy
    current_strategy_health = strategy_health if strategy_health is not None else _current_strategy_health(args)
    candidates = strategy.screen(frame)
    candidates = enrich_and_score_candidates(
        frame,
        candidates,
        settings.scoring.weights,
        sector_column=getattr(args, "sector_column", None),
        sector_top=sector_top if sector_top is not None else getattr(args, "sector_top", 5),
        only_top_sectors=only_top_sectors if only_top_sectors is not None else getattr(args, "only_top_sectors", False),
    )
    candidate_limit = top if top is not None else getattr(args, "top", None)
    if candidate_limit:
        candidates = candidates.head(candidate_limit)
    return apply_strategy_gate_to_candidates(candidates, current_strategy_health)


def run_screen(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    frame = limit_recent_history(frame, getattr(args, "lookback_days", None))
    frame = prefilter_dragon_universe(frame, args.strategy, getattr(args, "prefilter_symbols", None))
    strategy = None if getattr(args, "portfolio_config", None) else strategy_from_args(args)
    if strategy is not None:
        args._resolved_strategy = strategy
    settings = settings_from_args(args)
    current_strategy_health = {} if getattr(args, "portfolio_config", None) else _current_strategy_health(args)
    results = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=current_strategy_health,
    )
    rows = results.to_dict(orient="records")
    if args.record and _strategy_health_allows_new_positions(current_strategy_health):
        strategy_name = str(results.attrs.get("selection_strategy_name") or getattr(strategy, "name", "") or args.strategy)
        SelectionTracker(args.tracker, sqlite_path=getattr(args, "sqlite", None)).record_many(records_from_selection(strategy_name, rows))
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))

def run_dragon_screen(args: argparse.Namespace) -> None:
    args.strategy = "dragon_leader"
    args.config = None
    run_screen(args)

def run_dragon_check(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    frame = limit_recent_history(frame, getattr(args, "lookback_days", None))
    diagnostics = latest_dragon_diagnostics(frame, args.symbol)
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str))

def run_backtest(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv)
    strategy = strategy_from_args(args)
    engine = BacktestEngine(
        BacktestConfig(
            initial_cash=args.cash,
            buy_price_field=args.buy_price,
            execution_timing=getattr(args, "execution_timing", "next_bar"),
        )
    )
    result = engine.run(frame, strategy)
    print(json.dumps(result.summary(), ensure_ascii=False, indent=2))

def run_daily_report(args: argparse.Namespace) -> None:
    strategy = None
    selected: list[dict] = []
    risks = ["Live trading is not connected yet; selections are research and replay only."]
    market_view = "Waiting for intraday market data, index context, and news inputs."
    market_temperature = None
    allocation_plan = None
    data_health = None
    current_strategy_health: dict = {}

    if args.csv or (args.cache_dir and args.universe):
        frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
        strategy = None if getattr(args, "portfolio_config", None) else strategy_from_args(args)
        if strategy is not None:
            args._resolved_strategy = strategy
        settings = settings_from_args(args)
        current_strategy_health = {} if getattr(args, "portfolio_config", None) else _current_strategy_health(args)
        selected_frame = screened_candidates_from_args(
            args,
            frame,
            strategy=strategy,
            settings=settings,
            strategy_health=current_strategy_health,
        )
        selected = selected_frame.to_dict(orient="records")
        market_temperature = calculate_market_temperature(frame, selected_frame).to_dict()
        allocation_plan = build_allocation_plan(
            selected_frame,
            market_temperature,
            cash=args.cash,
            max_positions=args.max_positions,
            regime_exposure=settings.risk.regime_exposure,
            cap_by_risk=settings.risk.cap_by_risk,
            strategy_health=current_strategy_health,
        ).to_dict()
        data_health = check_ohlcv_health(frame, min_rows_per_symbol=30, max_stale_days=10).to_dict()
        if _strategy_health_allows_new_positions(current_strategy_health):
            strategy_name = str(selected_frame.attrs.get("selection_strategy_name") or getattr(strategy, "name", "") or args.strategy)
            SelectionTracker(args.tracker, sqlite_path=getattr(args, "sqlite", None)).record_many(records_from_selection(strategy_name, selected))
        market_view = f"Screening completed with {strategy.name}, {len(selected)} candidates selected."
        risks.append("This report currently uses technical data only and does not merge limit-up/down, suspensions, news, or sector strength.")
    else:
        settings = settings_from_args(args)

    market_context = build_market_context(settings).to_dict()

    experiment_summary = None
    if args.experiment_summary and args.experiment_summary.exists():
        experiment_summary = json.loads(args.experiment_summary.read_text(encoding="utf-8"))
    promotion_summary = summarize_promotion_records(_promotion_records_from_args(args), limit=5)
    strategy_health = _strategy_health_from_args(args)
    constraint_summary = _constraint_summary_from_args(args, limit=5)
    strategy_rotation = build_strategy_rotation(strategy_health, constraint_summary, promotion_summary)
    rotation_history = _rotation_history_from_args(args, limit=20)
    trade_records = _trade_records_from_args(args)
    trade_stats = summarize_trade_journal(trade_records)
    trade_plan_summary = build_trade_plan_summary(_trade_plan_records_from_args(args), limit=5)
    trade_plan_audit = summarize_trade_plan_audit(_trade_plan_records_from_args(args), trade_records, limit=5)
    action_execution_summary = _action_execution_summary_from_args(args, trade_records=trade_records, limit=5)
    exit_plan = _latest_exit_plan_from_args(args)
    exit_execution_summary = _exit_execution_summary_from_args(args, trade_records=trade_records, limit=5)
    lot_exit_execution_summary = _lot_exit_execution_summary_from_args(args, trade_records=trade_records, limit=5)
    lifecycle_snapshot = _position_lifecycle_snapshot_from_args(args, limit=5)
    gate_review = summarize_gate_journal(trade_records, limit=5)
    discipline_summary = _discipline_summary_from_args(args, limit=5)
    discipline_adherence = _discipline_adherence_summary_from_args(args, limit=5)
    pretrade_checks = _pretrade_preview_from_report_inputs(
        selected,
        allocation_plan,
        market_temperature,
        settings,
        current_strategy_health,
        cash=args.cash,
        max_positions=args.max_positions,
    )
    content = DailyReport().render(
        DailyReportInput(
            title="A-share Quant Daily Report",
            market_view=market_view,
            selected=selected,
            risks=risks,
            market_temperature=market_temperature,
            allocation_plan=allocation_plan,
            experiment_summary=experiment_summary,
            promotion_summary=promotion_summary,
            strategy_health=strategy_health,
            constraint_summary=constraint_summary,
            strategy_rotation=strategy_rotation,
            rotation_history=rotation_history,
            pretrade_checks=pretrade_checks,
            market_context=market_context,
            data_health=data_health,
            gate_review=gate_review,
            trade_stats=trade_stats,
            trade_plan_summary=trade_plan_summary,
            trade_plan_audit=trade_plan_audit,
            action_execution_summary=action_execution_summary,
            exit_plan=exit_plan,
            exit_execution_summary=exit_execution_summary,
            lot_exit_execution_summary=lot_exit_execution_summary,
            lifecycle_snapshot=lifecycle_snapshot,
            discipline_summary=discipline_summary,
            discipline_adherence=discipline_adherence,
        )
    )
    _persist_discipline_from_args(
        args,
        "report.daily",
        gate_review=gate_review,
        trade_stats=trade_stats,
        allocation_plan=allocation_plan,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(str(args.output))

def run_weekly_report(args: argparse.Namespace) -> None:
    settings = settings_from_args(args)
    market_temperature = None
    selection_summary: list[dict] = []
    gate_summary: list[dict] = []

    if args.csv:
        frame = read_ohlcv_csv(args.csv)
        strategy = strategy_from_args(args)
        args._resolved_strategy = strategy
        settings = settings_from_args(args)
        candidates = screened_candidates_from_args(
            args,
            frame,
            strategy=strategy,
            settings=settings,
            strategy_health=_current_strategy_health(args),
            only_top_sectors=False,
            top=None,
        )
        market_temperature = calculate_market_temperature(frame, candidates).to_dict()
        horizons = tuple(int(item.strip()) for item in args.horizons.split(",") if item.strip())
        if getattr(args, "sqlite", None):
            validation = pd.DataFrame(
                [result.to_dict() for result in validate_selections(_sqlite_selection_records(args.sqlite), frame, horizons=horizons)]
            )
        else:
            validation = validate_selection_file(args.tracker, args.csv, horizons=horizons)
        selection_summary = summarize_forward_returns(validation).to_dict(orient="records")
        gate_summary = summarize_forward_returns_by(validation, "entry_gate").to_dict(orient="records")

    market_context = build_market_context(settings).to_dict()
    trade_records = _trade_records_from_args(args)
    trade_stats = summarize_trade_journal(trade_records)
    trade_plan_summary = build_trade_plan_summary(_trade_plan_records_from_args(args), limit=10)
    trade_plan_audit = summarize_trade_plan_audit(_trade_plan_records_from_args(args), trade_records, limit=10)
    action_execution_summary = _action_execution_summary_from_args(args, trade_records=trade_records, limit=10)
    exit_plan = _latest_exit_plan_from_args(args)
    exit_execution_summary = _exit_execution_summary_from_args(args, trade_records=trade_records, limit=10)
    lot_exit_execution_summary = _lot_exit_execution_summary_from_args(args, trade_records=trade_records, limit=10)
    lifecycle_snapshot = _position_lifecycle_snapshot_from_args(args, limit=10)
    gate_review = summarize_gate_journal(trade_records, limit=10)
    discipline_summary = _discipline_summary_from_args(args, limit=10)
    discipline_adherence = _discipline_adherence_summary_from_args(args, limit=10)
    experiment_summary = None
    if args.experiment_summary and args.experiment_summary.exists():
        experiment_summary = json.loads(args.experiment_summary.read_text(encoding="utf-8"))
    promotion_summary = summarize_promotion_records(_promotion_records_from_args(args), limit=10)
    strategy_health = _strategy_health_from_args(args)
    constraint_summary = _constraint_summary_from_args(args, limit=10)
    approval_cooldown = _approval_cooldown_payload_from_args(args)
    strategy_rotation = build_strategy_rotation(strategy_health, constraint_summary, promotion_summary)
    rotation_history = _rotation_history_from_args(args, limit=20)
    content = WeeklyReport().render(
        WeeklyReportInput(
            title="A-share Quant Weekly Report",
            market_temperature=market_temperature,
            selection_summary=selection_summary,
            gate_summary=gate_summary,
            trade_stats=trade_stats,
            experiment_summary=experiment_summary,
            promotion_summary=promotion_summary,
            strategy_health=strategy_health,
            constraint_summary=constraint_summary,
            strategy_rotation=strategy_rotation,
            rotation_history=rotation_history,
            notes=args.note,
            market_context=market_context,
            gate_review=gate_review,
            trade_plan_summary=trade_plan_summary,
            trade_plan_audit=trade_plan_audit,
            action_execution_summary=action_execution_summary,
            exit_plan=exit_plan,
            exit_execution_summary=exit_execution_summary,
            lot_exit_execution_summary=lot_exit_execution_summary,
            lifecycle_snapshot=lifecycle_snapshot,
            discipline_summary=discipline_summary,
            discipline_adherence=discipline_adherence,
        )
    )
    _persist_discipline_from_args(
        args,
        "report.weekly",
        gate_review=gate_review,
        trade_stats=trade_stats,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(str(args.output))

def run_dragon_validation_report(args: argparse.Namespace) -> None:
    horizons = tuple(int(item.strip()) for item in args.horizons.split(",") if item.strip())
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    frame = limit_recent_history(frame, getattr(args, "lookback_days", None))
    frame = prefilter_dragon_universe(frame, "dragon_leader", getattr(args, "prefilter_symbols", None))
    selections = SelectionTracker(args.tracker).history()
    validation = pd.DataFrame([result.to_dict() for result in validate_selections(selections, frame, horizons=horizons)])
    signal_summary = summarize_forward_returns(validation).to_dict(orient="records")
    gate_summary = summarize_forward_returns_by(validation, "entry_gate").to_dict(orient="records")

    strategy = create_strategy(
        "dragon_leader",
        entry_gate=args.entry_gate,
        entry_model=args.dragon_entry_model,
        max_next_open_gap=args.max_next_open_gap,
        min_next_open_gap=args.min_next_open_gap,
        require_next_open_above_ma5=not args.allow_next_open_below_ma5,
    )
    args._resolved_strategy = strategy
    current_candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings_from_args(args),
        strategy_health=_current_strategy_health(args),
    )
    backtest_result = BacktestEngine(
        BacktestConfig(
            initial_cash=args.cash,
            buy_price_field=args.buy_price,
            execution_timing=getattr(args, "execution_timing", "next_bar"),
        )
    ).run(frame, strategy)
    content = DragonValidationReport().render(
        DragonValidationInput(
            title="龙头战法验证报告",
            entry_gate=args.entry_gate,
            entry_model=args.dragon_entry_model,
            buy_price=args.buy_price,
            signal_summary=signal_summary,
            gate_summary=gate_summary,
            backtest_summary=backtest_result.summary(),
            candidates=current_candidates.to_dict(orient="records"),
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(str(args.output))


def limit_recent_history(frame: pd.DataFrame, lookback_days: int | None) -> pd.DataFrame:
    if not lookback_days or lookback_days <= 0 or frame.empty or "date" not in frame.columns:
        return frame
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"])
    cutoff = data["date"].max().normalize() - pd.Timedelta(days=lookback_days)
    return data[data["date"] >= cutoff].copy()


def prefilter_dragon_universe(frame: pd.DataFrame, strategy_name: str, prefilter_symbols: int | None) -> pd.DataFrame:
    normalized = str(strategy_name).strip().lower().replace("-", "_")
    if normalized != "dragon_leader" or not prefilter_symbols or prefilter_symbols <= 0:
        return frame
    if frame.empty or "symbol" not in frame.columns or "date" not in frame.columns:
        return frame

    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"])
    latest = data.sort_values(["symbol", "date"]).groupby("symbol").tail(1).copy()
    required = {"close", "open", "high", "low", "volume"}
    if not required.issubset(latest.columns):
        return frame

    latest["range_pct"] = (pd.to_numeric(latest["high"], errors="coerce") - pd.to_numeric(latest["low"], errors="coerce")) / pd.to_numeric(latest["close"], errors="coerce")
    latest["day_return"] = pd.to_numeric(latest["close"], errors="coerce") / pd.to_numeric(latest["open"], errors="coerce") - 1.0
    if "momentum_20" not in latest.columns or "volume_ratio_20" not in latest.columns:
        latest = add_core_factors(data).sort_values(["symbol", "date"]).groupby("symbol").tail(1).copy()
        latest["range_pct"] = (pd.to_numeric(latest["high"], errors="coerce") - pd.to_numeric(latest["low"], errors="coerce")) / pd.to_numeric(latest["close"], errors="coerce")
        latest["day_return"] = pd.to_numeric(latest["close"], errors="coerce") / pd.to_numeric(latest["open"], errors="coerce") - 1.0

    latest["activity_score"] = (
        pd.to_numeric(latest.get("volume_ratio_20"), errors="coerce").fillna(0).clip(lower=0, upper=8) * 0.45
        + pd.to_numeric(latest.get("momentum_20"), errors="coerce").fillna(0).clip(lower=-0.2, upper=1.2) * 100 * 0.25
        + pd.to_numeric(latest.get("range_pct"), errors="coerce").fillna(0).clip(lower=0, upper=0.3) * 100 * 0.20
        + pd.to_numeric(latest.get("day_return"), errors="coerce").fillna(0).clip(lower=-0.15, upper=0.3) * 100 * 0.10
    )
    keep = latest.sort_values("activity_score", ascending=False).head(prefilter_symbols)["symbol"].astype(str).tolist()
    return data[data["symbol"].astype(str).isin(keep)].copy()

def run_briefing_report(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    current_strategy_health = _current_strategy_health(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=current_strategy_health,
        only_top_sectors=False,
        sector_top=args.top,
    )

    market_temperature = calculate_market_temperature(frame, candidates).to_dict()
    allocation_plan = build_allocation_plan(
        candidates,
        market_temperature,
        cash=args.cash,
        max_positions=args.top,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=current_strategy_health,
    ).to_dict()
    prices = parse_price_overrides(args.price)
    stops = parse_price_overrides(args.stop)
    trade_records = _trade_records_from_args(args)
    position_book_model = build_position_book(trade_records, cash=args.cash, prices=prices)
    position_book = position_book_model.to_dict()
    lot_book = build_lot_book(trade_records, prices=prices, as_of=getattr(args, "as_of", None)).to_dict()
    holding_risk_model = check_holding_risk(
        position_book_model,
        stops=stops,
        max_exposure_pct=args.max_exposure_pct,
        max_position_pct=args.max_position_pct,
    )
    holding_risk = holding_risk_model.to_dict()
    holding_action_plan = build_position_action_plan(
        position_book_model,
        holding_risk_model,
        stops=stops,
        max_exposure_pct=args.max_exposure_pct,
        max_position_pct=args.max_position_pct,
        target_exposure_pct=float(allocation_plan.get("target_exposure_pct", 0) or 0),
    ).to_dict()
    exit_plan = build_exit_plan(
        position_book_model,
        trade_records=trade_records,
        stops=stops,
        targets=parse_price_overrides(getattr(args, "target", []) or []),
        invalidated=parse_kv_pairs(getattr(args, "invalidate", []) or []),
        max_position_pct=getattr(args, "max_position_pct", 0.2),
        max_holding_days=getattr(args, "max_holding_days", 20),
        time_stop_min_return_pct=getattr(args, "time_stop_min_return_pct", 0.0),
        profit_take_pct=getattr(args, "profit_take_pct", 0.5),
        plan_date=getattr(args, "as_of", None),
    ).to_dict()
    sectors = calculate_sector_strength(
        frame,
        candidates,
        sector_column=args.sector_column,
        top=args.sector_top,
    ).to_dict(orient="records")
    dragon_frame = limit_recent_history(frame, 60)
    dragon_frame = prefilter_dragon_universe(dragon_frame, "dragon_leader", 400)
    dragon_strategy = create_strategy("dragon_leader")
    dragon_candidates = dragon_strategy.screen(dragon_frame)
    dragon_candidates = enrich_and_score_candidates(
        dragon_frame,
        dragon_candidates,
        settings.scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.sector_top,
        only_top_sectors=False,
    )
    dragon_candidates = dragon_candidates.head(min(int(args.top or 5), 5))
    market_context = build_market_context(settings).to_dict()
    data_health = check_ohlcv_health(frame, min_rows_per_symbol=30, max_stale_days=10).to_dict()
    experiment_summary = None
    if args.experiment_summary and args.experiment_summary.exists():
        experiment_summary = json.loads(args.experiment_summary.read_text(encoding="utf-8"))
    promotion_summary = summarize_promotion_records(_promotion_records_from_args(args), limit=10)
    strategy_health = _strategy_health_from_args(args)
    constraint_summary = _constraint_summary_from_args(args, limit=10)
    strategy_rotation = build_strategy_rotation(strategy_health, constraint_summary, promotion_summary)
    rotation_history = _rotation_history_from_args(args, limit=20)
    trade_stats = summarize_trade_journal(trade_records)
    trade_plan_summary = build_trade_plan_summary(_trade_plan_records_from_args(args), limit=10)
    trade_plan_audit = summarize_trade_plan_audit(_trade_plan_records_from_args(args), trade_records, limit=10)
    action_execution_summary = _action_execution_summary_from_args(args, trade_records=trade_records, limit=10)
    exit_execution_summary = _exit_execution_summary_from_args(args, trade_records=trade_records, limit=10)
    lot_exit_execution_summary = _lot_exit_execution_summary_from_args(args, trade_records=trade_records, limit=10)
    lifecycle_snapshot = _position_lifecycle_snapshot_from_args(args, limit=10)
    gate_review = summarize_gate_journal(trade_records, limit=5)
    discipline_summary = _discipline_summary_from_args(args, limit=5)
    discipline_adherence = _discipline_adherence_summary_from_args(args, limit=5)
    pretrade_checks = _pretrade_preview_from_report_inputs(
        candidates.to_dict(orient="records"),
        allocation_plan,
        market_temperature,
        settings,
        current_strategy_health,
        cash=args.cash,
        max_positions=args.top,
    )
    content = BriefingReport().render(
        BriefingInput(
            title="A-share Trading Briefing",
            market_temperature=market_temperature,
            candidates=candidates.to_dict(orient="records"),
            allocation_plan=allocation_plan,
            position_book=position_book,
            lot_book=lot_book,
            holding_risk=holding_risk,
            holding_action_plan=holding_action_plan,
            dragon_candidates=dragon_candidates.to_dict(orient="records"),
            sectors=sectors,
            experiment_summary=experiment_summary,
            promotion_summary=promotion_summary,
            strategy_health=strategy_health,
            constraint_summary=constraint_summary,
            strategy_rotation=strategy_rotation,
            rotation_history=rotation_history,
            pretrade_checks=pretrade_checks,
            market_context=market_context,
            data_health=data_health,
            gate_review=gate_review,
            trade_stats=trade_stats,
            trade_plan_summary=trade_plan_summary,
            trade_plan_audit=trade_plan_audit,
            action_execution_summary=action_execution_summary,
            exit_plan=exit_plan,
            exit_execution_summary=exit_execution_summary,
            lot_exit_execution_summary=lot_exit_execution_summary,
            lifecycle_snapshot=lifecycle_snapshot,
            discipline_summary=discipline_summary,
        )
    )
    _persist_discipline_from_args(
        args,
        "report.briefing",
        gate_review=gate_review,
        trade_stats=trade_stats,
        holding_risk=holding_risk,
        allocation_plan=allocation_plan,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(str(args.output))


def _render_premarket_report_from_context(context: dict) -> str:
    return PremarketReport().render(
        PremarketReportInput(
            title="A-share Premarket Report",
            market_temperature=context["market_temperature"],
            market_context=context["market_context"],
            data_health=context["data_health"],
            candidates=context["candidates"],
            allocation_plan=context["allocation_plan"],
            pretrade_checks=context["pretrade_checks"],
            position_book=context["position_book"],
            lot_book=context.get("lot_book"),
            holding_risk=context["holding_risk"],
            holding_action_plan=context.get("holding_action_plan"),
            exit_plan=context.get("exit_plan"),
            strategy_health=context["strategy_health"],
            constraint_summary=context["constraint_summary"],
            strategy_rotation=context["strategy_rotation"],
            strategy_portfolio=context.get("strategy_portfolio"),
            rotation_history=context["rotation_history"],
            gate_review=context.get("gate_review"),
            trade_stats=context.get("trade_stats"),
            action_execution_summary=context.get("action_execution_summary"),
            exit_execution_summary=context.get("exit_execution_summary"),
            lot_exit_execution_summary=context.get("lot_exit_execution_summary"),
            lifecycle_snapshot=context.get("lifecycle_snapshot"),
            discipline_summary=context.get("discipline_summary"),
            discipline_adherence=context.get("discipline_adherence"),
            final_battle_plan=context.get("final_battle_plan"),
        )
    )


def run_premarket_report(args: argparse.Namespace, *, print_path: bool = True, context: dict | None = None) -> None:
    context = context or _premarket_context_from_args(args)
    content = _render_premarket_report_from_context(context)
    if getattr(args, "command", "") != "workflow":
        _persist_discipline_from_args(
            args,
            "report.premarket",
            gate_review=context.get("gate_review"),
            trade_stats=context.get("trade_stats"),
            holding_risk=context.get("holding_risk"),
            allocation_plan=context.get("allocation_plan"),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    if print_path:
        print(str(args.output))


def run_battle_plan_report(args: argparse.Namespace) -> None:
    context = _premarket_context_from_args(args)
    plan = context.get("final_battle_plan") or build_final_battle_plan(context)
    if getattr(args, "format", "markdown") == "json":
        text = json.dumps(plan, ensure_ascii=False, indent=2, default=str)
    else:
        text = render_final_battle_plan_markdown(plan)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_cockpit_report(args: argparse.Namespace) -> None:
    context = _premarket_context_from_args(args)
    trade_records = _trade_records_from_args(args)
    trade_plan_records = _trade_plan_records_from_args(args)
    confirm_records = _execution_confirmation_records_from_args(args)
    execution_audit = summarize_execution_audit(
        confirm_records,
        trade_records,
        lookahead_days=getattr(args, "lookahead_days", 1),
        limit=getattr(args, "top", 5),
    )
    trade_plan_audit = summarize_trade_plan_audit(trade_plan_records, trade_records, limit=getattr(args, "top", 5))
    gate_review = summarize_gate_journal(trade_records, limit=getattr(args, "top", 5))
    cockpit = build_trading_cockpit(
        context,
        execution_audit=execution_audit,
        trade_plan_audit=trade_plan_audit,
        gate_review=gate_review,
        execution_confirmations=confirm_records,
        approval_cooldown=context.get("approval_cooldown"),
        limit=max(int(getattr(args, "top", 5) or 5), 1),
    )
    if getattr(args, "format", "markdown") == "json":
        text = json.dumps(cockpit, ensure_ascii=False, indent=2, default=str)
    else:
        text = render_trading_cockpit_markdown(cockpit)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_timeline_report(args: argparse.Namespace) -> None:
    context = _premarket_context_from_args(args)
    settings = settings_from_args(args)
    trade_records = _trade_records_from_args(args)
    confirm_records = _execution_confirmation_records_from_args(args)
    execution_audit = summarize_execution_audit(
        confirm_records,
        trade_records,
        lookahead_days=getattr(args, "lookahead_days", 1),
        limit=getattr(args, "top", 5),
    )
    timeline = build_trading_day_timeline(
        now=_timeline_now_from_args(args),
        final_battle_plan=context.get("final_battle_plan"),
        execution_confirmations=confirm_records,
        trade_records=trade_records,
        execution_audit=execution_audit,
        lifecycle_snapshot=context.get("lifecycle_snapshot"),
        gate_review=context.get("gate_review"),
        approval_cooldown=context.get("approval_cooldown"),
    )
    timeline = apply_trading_day_template(timeline, settings.trading_day.phases)
    _persist_trading_day_state_from_args(args, "report.timeline", timeline)
    if getattr(args, "format", "markdown") == "json":
        text = json.dumps(timeline, ensure_ascii=False, indent=2, default=str)
    else:
        text = render_trading_day_timeline_markdown(timeline)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_assistant_report(args: argparse.Namespace) -> None:
    context = _premarket_context_from_args(args)
    settings = settings_from_args(args)
    trade_records = _trade_records_from_args(args)
    trade_plan_records = _trade_plan_records_from_args(args)
    confirm_records = _execution_confirmation_records_from_args(args)
    execution_audit = summarize_execution_audit(
        confirm_records,
        trade_records,
        lookahead_days=getattr(args, "lookahead_days", 1),
        limit=getattr(args, "top", 5),
    )
    trade_plan_audit = summarize_trade_plan_audit(trade_plan_records, trade_records, limit=getattr(args, "top", 5))
    gate_review = summarize_gate_journal(trade_records, limit=getattr(args, "top", 5))
    cockpit = build_trading_cockpit(
        context,
        execution_audit=execution_audit,
        trade_plan_audit=trade_plan_audit,
        gate_review=gate_review,
        execution_confirmations=confirm_records,
        approval_cooldown=context.get("approval_cooldown"),
        limit=max(int(getattr(args, "top", 5) or 5), 1),
    )
    battle_plan = context.get("final_battle_plan") or build_final_battle_plan(context)
    timeline = build_trading_day_timeline(
        now=_timeline_now_from_args(args),
        final_battle_plan=battle_plan,
        execution_confirmations=confirm_records,
        trade_records=trade_records,
        execution_audit=execution_audit,
        lifecycle_snapshot=context.get("lifecycle_snapshot"),
        gate_review=gate_review,
        approval_cooldown=context.get("approval_cooldown"),
    )
    timeline = apply_trading_day_template(timeline, settings.trading_day.phases)
    state = _persist_trading_day_state_from_args(args, "report.assistant", timeline)
    watchdog = _trading_day_watchdog_from_args(args, state)
    assistant = build_trading_assistant(
        context={**context, "final_battle_plan": battle_plan},
        cockpit=cockpit,
        timeline=timeline,
        watchdog=watchdog,
        state=state,
        limit=max(int(getattr(args, "top", 5) or 5), 1),
    )
    if getattr(args, "format", "markdown") == "json":
        text = json.dumps(assistant, ensure_ascii=False, indent=2, default=str)
    else:
        text = render_trading_assistant_markdown(assistant)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def _timeline_now_from_args(args: argparse.Namespace) -> datetime | None:
    value = str(getattr(args, "as_of", "") or "").strip()
    if not value:
        return None
    if len(value) == 10:
        value = f"{value}T15:30:00"
    return datetime.fromisoformat(value)


def _premarket_context_from_args(
    args: argparse.Namespace,
    *,
    frame: pd.DataFrame | None = None,
    data_health: dict | None = None,
) -> dict:
    frame = frame if frame is not None else load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    factor_frame = add_core_factors(frame)
    strategy = None if getattr(args, "portfolio_config", None) else strategy_from_args(args)
    if strategy is not None:
        args._resolved_strategy = strategy
    settings = settings_from_args(args)
    current_strategy_health = {} if getattr(args, "portfolio_config", None) else _current_strategy_health(args)
    candidates = screened_candidates_from_args(
        args,
        factor_frame,
        strategy=strategy,
        settings=settings,
        strategy_health=current_strategy_health,
        only_top_sectors=False,
    )
    market_temperature = calculate_market_temperature(factor_frame, candidates).to_dict()
    max_positions = int(getattr(args, "max_positions", None) or getattr(args, "top", 5) or 5)
    allocation_plan = build_allocation_plan(
        candidates,
        market_temperature,
        cash=args.cash,
        max_positions=max_positions,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=current_strategy_health,
    ).to_dict()
    prices = parse_price_overrides(args.price)
    stops = parse_price_overrides(args.stop)
    trade_records = _trade_records_from_args(args)
    position_book_model = build_position_book(trade_records, cash=args.cash, prices=prices)
    position_book = position_book_model.to_dict()
    lot_book = build_lot_book(trade_records, prices=prices, as_of=getattr(args, "as_of", None)).to_dict()
    holding_risk_model = check_holding_risk(
        position_book_model,
        stops=stops,
        max_exposure_pct=args.max_exposure_pct,
        max_position_pct=args.max_position_pct,
    )
    holding_risk = holding_risk_model.to_dict()
    holding_action_plan = build_position_action_plan(
        position_book_model,
        holding_risk_model,
        stops=stops,
        max_exposure_pct=args.max_exposure_pct,
        max_position_pct=args.max_position_pct,
        target_exposure_pct=float(allocation_plan.get("target_exposure_pct", 0) or 0),
    ).to_dict()
    exit_plan = build_exit_plan(
        position_book_model,
        trade_records=trade_records,
        stops=stops,
        targets=parse_price_overrides(getattr(args, "target", []) or []),
        invalidated=parse_kv_pairs(getattr(args, "invalidate", []) or []),
        max_position_pct=getattr(args, "max_position_pct", 0.2),
        max_holding_days=getattr(args, "max_holding_days", 20),
        time_stop_min_return_pct=getattr(args, "time_stop_min_return_pct", 0.0),
        profit_take_pct=getattr(args, "profit_take_pct", 0.5),
        plan_date=getattr(args, "as_of", None),
    ).to_dict()
    market_context = build_market_context(settings).to_dict()
    if data_health is None:
        data_health = check_ohlcv_health(
            frame,
            min_rows_per_symbol=int(getattr(args, "min_rows", 30) or 30),
            max_stale_days=getattr(args, "max_stale_days", 10),
            as_of=getattr(args, "as_of", None),
        ).to_dict()
    promotion_summary = summarize_promotion_records(_promotion_records_from_args(args), limit=10)
    strategy_health = _strategy_health_from_args(args)
    constraint_summary = _constraint_summary_from_args(args, limit=10)
    strategy_rotation = build_strategy_rotation(strategy_health, constraint_summary, promotion_summary)
    rotation_history = _rotation_history_from_args(args, limit=20)
    trade_stats = summarize_trade_journal(trade_records)
    lifecycle_rule_plan = build_lifecycle_rule_plan(
        position_book_model,
        stops=stops,
        discipline_summary=trade_stats,
        max_probe_pct=getattr(args, "max_probe_pct", 0.05),
        max_position_pct=getattr(args, "max_position_pct", 0.2),
        add_step_pct=getattr(args, "add_step_pct", 0.05),
        add_profit_trigger_pct=getattr(args, "add_profit_trigger_pct", 0.03),
        reduce_loss_warning_pct=getattr(args, "reduce_loss_warning_pct", 0.03),
    ).to_dict()
    gate_review = summarize_gate_journal(trade_records, limit=5)
    action_execution_summary = _action_execution_summary_from_args(args, trade_records=trade_records, limit=5)
    exit_execution_summary = _exit_execution_summary_from_args(args, trade_records=trade_records, limit=5)
    lot_exit_execution_summary = _lot_exit_execution_summary_from_args(args, trade_records=trade_records, limit=5)
    lifecycle_snapshot = build_position_lifecycle_snapshot(
        trade_plan_summary=build_trade_plan_summary(_trade_plan_records_from_args(args), limit=5),
        lot_book=lot_book,
        holding_action_plan=holding_action_plan,
        exit_plan=exit_plan,
        lifecycle_rule_plan=lifecycle_rule_plan,
        trade_plan_audit=summarize_trade_plan_audit(_trade_plan_records_from_args(args), trade_records, limit=5),
        action_execution_summary=action_execution_summary,
        exit_execution_summary=exit_execution_summary,
        lot_exit_execution_summary=lot_exit_execution_summary,
    )
    discipline_summary = _discipline_summary_from_args(args, limit=5)
    discipline_adherence = _discipline_adherence_summary_from_args(args, limit=5)
    pretrade_checks = _pretrade_preview_from_report_inputs(
        candidates.to_dict(orient="records"),
        allocation_plan,
        market_temperature,
        settings,
        current_strategy_health,
        cash=args.cash,
        max_positions=max_positions,
    )
    approval_cooldown = _approval_cooldown_payload_from_args(args)
    context = {
        "market_temperature": market_temperature,
        "market_context": market_context,
        "data_health": data_health,
        "candidates": candidates.to_dict(orient="records"),
        "allocation_plan": allocation_plan,
        "pretrade_checks": pretrade_checks,
        "position_book": position_book,
        "lot_book": lot_book,
        "holding_risk": holding_risk,
        "holding_action_plan": holding_action_plan,
        "exit_plan": exit_plan,
        "lifecycle_rule_plan": lifecycle_rule_plan,
        "strategy_health": strategy_health,
        "constraint_summary": constraint_summary,
        "approval_cooldown": approval_cooldown,
        "strategy_rotation": strategy_rotation,
        "strategy_portfolio": candidates.attrs.get("strategy_portfolio_plan", {}),
        "rotation_history": rotation_history,
        "gate_review": gate_review,
        "trade_stats": trade_stats,
        "action_execution_summary": action_execution_summary,
        "exit_execution_summary": exit_execution_summary,
        "lot_exit_execution_summary": lot_exit_execution_summary,
        "lifecycle_snapshot": lifecycle_snapshot,
        "discipline_summary": discipline_summary,
        "discipline_adherence": discipline_adherence,
    }
    context["final_battle_plan"] = build_final_battle_plan(context, limit=max_positions)
    return context


def run_workflow_premarket(args: argparse.Namespace) -> None:
    summary = {
        "status": "ok",
        "steps": [],
        "outputs": {"premarket_report": str(args.output)},
    }
    if args.refresh_cache:
        if not args.universe:
            summary["status"] = "fail"
            summary["steps"].append({"name": "refresh_cache", "status": "fail", "message": "--refresh-cache requires --universe"})
            _finish_workflow_summary(args, summary)
            raise SystemExit(1)
        if not args.refresh_start:
            summary["status"] = "fail"
            summary["steps"].append({"name": "refresh_cache", "status": "fail", "message": "--refresh-cache requires --refresh-start"})
            _finish_workflow_summary(args, summary)
            raise SystemExit(1)
        refresh = fetch_batch_summary(
            universe=args.universe,
            start=args.refresh_start,
            end=args.refresh_end or date.today().strftime("%Y%m%d"),
            adjust=args.adjust,
            cache_dir=args.cache_dir,
            manifest_path=args.manifest,
            source=args.source,
            limit=args.limit,
            refresh=True,
            refresh_stale_days=args.refresh_stale_days,
        )
        refresh_status = "ok" if int(refresh.get("failed", 0)) == 0 else "warn"
        summary["steps"].append({"name": "refresh_cache", "status": refresh_status, "summary": refresh})
        if refresh_status == "warn":
            summary["status"] = "warn"
    else:
        summary["steps"].append({"name": "refresh_cache", "status": "skipped", "message": "pass --refresh-cache to refresh daily cache"})

    try:
        frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe, strict=args.strict)
    except (FileNotFoundError, ValueError) as exc:
        summary["status"] = "fail"
        summary["steps"].append({"name": "load_data", "status": "fail", "message": str(exc)})
        _finish_workflow_summary(args, summary)
        raise SystemExit(1)

    health = check_ohlcv_health(
        frame,
        min_rows_per_symbol=args.min_rows,
        max_stale_days=args.max_stale_days,
        as_of=args.as_of,
    ).to_dict()
    summary["steps"].append({"name": "data_health", "status": health.get("status", ""), "summary": health})
    if health.get("status") == "fail":
        summary["status"] = "fail"
    elif health.get("status") == "warn" and summary["status"] == "ok":
        summary["status"] = "warn"

    repair_plan = build_ohlcv_repair_plan(
        frame,
        min_rows_per_symbol=args.min_rows,
        max_stale_days=args.max_stale_days,
        as_of=args.as_of,
    )
    summary["steps"].append({"name": "repair_plan", "status": repair_plan.get("status", ""), "summary": repair_plan})
    if repair_plan.get("status") == "action_needed" and summary["status"] == "ok":
        summary["status"] = "warn"

    approval_cooldown = _record_auto_approval_cooldown_from_args(args)
    summary["approval_cooldown"] = {
        "status": approval_cooldown.get("status", "pass"),
        "constraint_count": int(approval_cooldown.get("constraint_count", 0) or 0),
        "persisted_count": int(approval_cooldown.get("persisted_count", 0) or 0),
        "skipped_existing_count": int(approval_cooldown.get("skipped_existing_count", 0) or 0),
    }
    summary["steps"].append({"name": "approval_cooldown", "status": approval_cooldown.get("status", "pass"), "summary": approval_cooldown})
    summary["status"] = _merge_workflow_status(summary["status"], str(approval_cooldown.get("status", "pass") or "pass"))

    context = _premarket_context_from_args(args, frame=frame, data_health=health)
    gate = _workflow_execution_gate(health, repair_plan, context)
    battle_plan = context.get("final_battle_plan") or build_final_battle_plan(context)
    summary["gate"] = gate
    summary["battle_plan"] = {
        "status": battle_plan.get("status", ""),
        "decision": battle_plan.get("decision", ""),
        "must_do_count": len(list(battle_plan.get("must_do") or [])),
        "buy_candidate_count": len(list(battle_plan.get("buy_candidates") or [])),
        "blocked_candidate_count": len(list(battle_plan.get("blocked_candidates") or [])),
    }
    summary["steps"].append({"name": "execution_gate", "status": gate["status"], "summary": gate})
    if gate["status"] == "block":
        summary["status"] = "block" if summary["status"] != "fail" else "fail"
    elif gate["status"] == "warn" and summary["status"] == "ok":
        summary["status"] = "warn"

    run_premarket_report(args, print_path=False, context=context)
    summary["steps"].append({"name": "premarket_report", "status": "ok", "path": str(args.output)})
    battle_plan_output = getattr(args, "battle_plan_output", None)
    if battle_plan_output:
        battle_plan_output.parent.mkdir(parents=True, exist_ok=True)
        battle_plan_output.write_text(render_final_battle_plan_markdown(battle_plan) + "\n", encoding="utf-8")
        summary["outputs"]["battle_plan"] = str(battle_plan_output)
        summary["steps"].append({"name": "battle_plan", "status": "ok", "path": str(battle_plan_output)})
    if getattr(args, "record_actions", False):
        append_position_action_plan_record(args.action_log, context.get("holding_action_plan") or {})
        summary["steps"].append({"name": "holding_action_plan", "status": "ok", "path": str(args.action_log)})
    if getattr(args, "record_exit_plan", False):
        append_exit_plan_record(args.exit_log, context.get("exit_plan") or {})
        summary["steps"].append({"name": "exit_plan", "status": "ok", "path": str(args.exit_log)})
    if getattr(args, "record_discipline", False):
        _persist_discipline_from_args(
            args,
            "workflow.premarket",
            gate_review=context.get("gate_review"),
            trade_stats=context.get("trade_stats"),
            holding_risk=context.get("holding_risk"),
            allocation_plan=context.get("allocation_plan"),
        )
        summary["steps"].append({"name": "discipline_record", "status": "ok", "path": str(getattr(args, "discipline_log", ""))})
    _finish_workflow_summary(args, summary)


def run_workflow_trading_day(args: argparse.Namespace) -> None:
    summary = {
        "status": "ok",
        "steps": [],
        "outputs": {
            "premarket_report": str(args.premarket_output),
            "battle_plan": str(args.battle_plan_output),
            "cockpit": str(args.cockpit_output),
            "execution_audit": str(args.execution_audit_output),
            "lifecycle": str(args.lifecycle_output),
            "timeline": str(args.timeline_output),
            "assistant": str(args.assistant_output),
            "daily_brief": str(args.daily_output),
            "trade_plan_batch": str(args.trade_plan_batch_output),
            "review_doctor": str(args.review_doctor_output),
            "review_attribution": str(args.review_attribution_output),
            "attribution_policy": str(args.attribution_policy_output),
            "summary": str(args.summary_output),
        },
    }
    try:
        frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe, strict=args.strict)
    except (FileNotFoundError, ValueError) as exc:
        summary["status"] = "fail"
        summary["steps"].append({"name": "load_data", "status": "fail", "message": str(exc)})
        _finish_workflow_summary(args, summary)
        raise SystemExit(1)

    health = check_ohlcv_health(
        frame,
        min_rows_per_symbol=args.min_rows,
        max_stale_days=args.max_stale_days,
        as_of=args.as_of,
    ).to_dict()
    summary["steps"].append({"name": "data_health", "status": health.get("status", ""), "summary": health})
    if health.get("status") == "fail":
        summary["status"] = "fail"
    elif health.get("status") == "warn":
        summary["status"] = "warn"

    repair_plan = build_ohlcv_repair_plan(
        frame,
        min_rows_per_symbol=args.min_rows,
        max_stale_days=args.max_stale_days,
        as_of=args.as_of,
    )
    summary["steps"].append({"name": "repair_plan", "status": repair_plan.get("status", ""), "summary": repair_plan})
    if repair_plan.get("status") == "action_needed" and summary["status"] == "ok":
        summary["status"] = "warn"

    approval_cooldown = _record_auto_approval_cooldown_from_args(args)
    summary["approval_cooldown"] = {
        "status": approval_cooldown.get("status", "pass"),
        "constraint_count": int(approval_cooldown.get("constraint_count", 0) or 0),
        "persisted_count": int(approval_cooldown.get("persisted_count", 0) or 0),
        "skipped_existing_count": int(approval_cooldown.get("skipped_existing_count", 0) or 0),
    }
    summary["steps"].append({"name": "approval_cooldown", "status": approval_cooldown.get("status", "pass"), "summary": approval_cooldown})
    summary["status"] = _merge_workflow_status(summary["status"], str(approval_cooldown.get("status", "pass") or "pass"))

    context = _premarket_context_from_args(args, frame=frame, data_health=health)
    settings = settings_from_args(args)
    battle_plan = context.get("final_battle_plan") or build_final_battle_plan(context)
    workflow_gate = _workflow_execution_gate(health, repair_plan, context)
    current_strategy_health = {}
    if not getattr(args, "portfolio_config", None):
        for item in list(context.get("strategy_health") or []):
            if str(item.get("strategy", "") or "") == str(getattr(args, "strategy", "") or ""):
                current_strategy_health = item
                break
    max_positions = max(int(getattr(args, "max_positions", None) or getattr(args, "top", 5) or 5), 1)
    trade_plan_batch = build_trade_plan_batch(
        candidates=pd.DataFrame(context.get("candidates") or []),
        market_temperature=context.get("market_temperature") or {},
        cash=args.cash,
        max_positions=max_positions,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=current_strategy_health,
        trade_date=str(getattr(args, "as_of", "") or "")[:10] or None,
    )
    trade_plan_persistence = {"persisted_count": 0, "skipped_existing_count": 0}
    if getattr(args, "record_trade_plans", False):
        trade_plan_persistence = append_unique_trade_plan_records(
            args.trade_plan_log,
            trade_plan_batch.plans,
            sqlite_path=getattr(args, "sqlite", None),
        )

    trade_records = _trade_records_from_args(args)
    trade_plan_records = _trade_plan_records_from_args(args)
    confirm_records = _execution_confirmation_records_from_args(args)
    execution_audit = summarize_execution_audit(
        confirm_records,
        trade_records,
        lookahead_days=getattr(args, "lookahead_days", 1),
        limit=max(int(getattr(args, "top", 5) or 5), 1),
    )
    trade_plan_audit = summarize_trade_plan_audit(
        trade_plan_records,
        trade_records,
        limit=max(int(getattr(args, "top", 5) or 5), 1),
    )
    gate_review = summarize_gate_journal(trade_records, limit=max(int(getattr(args, "top", 5) or 5), 1))
    cockpit = build_trading_cockpit(
        context,
        execution_audit=execution_audit,
        trade_plan_audit=trade_plan_audit,
        gate_review=gate_review,
        execution_confirmations=confirm_records,
        approval_cooldown=context.get("approval_cooldown"),
        limit=max(int(getattr(args, "top", 5) or 5), 1),
    )
    timeline = build_trading_day_timeline(
        now=_timeline_now_from_args(args),
        final_battle_plan=battle_plan,
        execution_confirmations=confirm_records,
        trade_records=trade_records,
        execution_audit=execution_audit,
        lifecycle_snapshot=context.get("lifecycle_snapshot"),
        gate_review=gate_review,
        approval_cooldown=context.get("approval_cooldown"),
    )
    timeline = apply_trading_day_template(timeline, settings.trading_day.phases)
    lifecycle_snapshot = context.get("lifecycle_snapshot") or {}
    state = _persist_trading_day_state_from_args(args, "workflow.trading-day", timeline)
    watchdog = _trading_day_watchdog_from_args(args, state)
    state_records = list(_trading_day_state_records_from_args(args))
    current_state_fingerprint = _record_fingerprint(state)
    if all(_record_fingerprint(record) != current_state_fingerprint for record in state_records):
        state_records.append(state)
    review_doctor = _review_doctor_from_args(
        args,
        lifecycle_snapshots=_merge_lifecycle_snapshots(_lifecycle_snapshot_records_from_args(args), lifecycle_snapshot),
        trading_day_states=state_records,
    )
    assistant = build_trading_assistant(
        context={**context, "final_battle_plan": battle_plan},
        cockpit=cockpit,
        timeline=timeline,
        watchdog=watchdog,
        state=state,
        limit=max(int(getattr(args, "top", 5) or 5), 1),
    )
    review_attribution = build_review_attribution_report(
        trade_plan_audit=trade_plan_audit,
        execution_audit=execution_audit,
        approval_audit=dict(approval_cooldown.get("approval_audit") or {}),
        approval_cooldown=approval_cooldown,
        gate_review=gate_review,
        trade_stats=context.get("trade_stats") or summarize_trade_journal(trade_records),
        lifecycle_snapshot=lifecycle_snapshot,
        limit=max(int(getattr(args, "top", 5) or 5), 1),
    )
    attribution_policy = build_attribution_policy(
        review_attribution,
        default_strategy=getattr(args, "strategy", "") or "manual_order",
        effective_date=getattr(args, "attribution_policy_date", ""),
    )
    attribution_policy_persistence = {}
    if getattr(args, "record_attribution_policy", False):
        attribution_policy_persistence = _persist_attribution_policy(args, attribution_policy)

    summary["gate"] = workflow_gate
    summary["battle_plan"] = {
        "status": battle_plan.get("status", ""),
        "decision": battle_plan.get("decision", ""),
        "must_do_count": len(list(battle_plan.get("must_do") or [])),
        "buy_candidate_count": len(list(battle_plan.get("buy_candidates") or [])),
        "blocked_candidate_count": len(list(battle_plan.get("blocked_candidates") or [])),
    }
    summary["trade_plan_batch"] = {
        "status": trade_plan_batch.status,
        "gate_status": trade_plan_batch.gate_status,
        "candidate_count": trade_plan_batch.total_candidates,
        "plan_count": trade_plan_batch.total_plans,
        **trade_plan_persistence,
    }
    summary["review_doctor"] = {
        "status": review_doctor.get("status", "pass"),
        "issue_count": len(list(review_doctor.get("issues") or [])),
        "counts": review_doctor.get("counts", {}),
    }
    summary["execution_audit"] = {
        "status": "block" if int(execution_audit.get("block_count", 0) or 0) > 0 else ("warn" if int(execution_audit.get("warn_count", 0) or 0) > 0 else "pass"),
        "missing_trade_writeback_count": int(execution_audit.get("missing_trade_writeback_count", 0) or 0),
        "missing_confirmation_trade_count": int(execution_audit.get("missing_confirmation_trade_count", 0) or 0),
        "fallback_link_count": int(execution_audit.get("fallback_link_count", 0) or 0),
    }
    summary["cockpit"] = {
        "status": cockpit.get("status", ""),
        "decision": cockpit.get("decision", ""),
        "action_item_count": len(list(cockpit.get("action_items") or [])),
    }
    summary["timeline"] = {
        "status": timeline.get("status", ""),
        "action_item_count": len(list(timeline.get("action_items") or [])),
    }
    summary["assistant"] = {
        "status": assistant.get("status", ""),
        "urgent_action_count": len(list(assistant.get("urgent_actions") or [])),
    }
    summary["review_attribution"] = {
        "status": review_attribution.get("status", "pass"),
        "score": int(review_attribution.get("score", 100) or 0),
        "root_cause_count": int(review_attribution.get("root_cause_count", 0) or 0),
        "by_area": review_attribution.get("by_area", {}),
    }
    summary["attribution_policy"] = {
        "status": attribution_policy.get("status", "pass"),
        "constraint_count": int(attribution_policy.get("constraint_count", 0) or 0),
        **attribution_policy_persistence,
    }
    daily_brief = build_daily_trade_brief(
        workflow_summary=summary,
        battle_plan=battle_plan,
        cockpit=cockpit,
        assistant=assistant,
        trade_plan_batch=trade_plan_batch,
        review_doctor=review_doctor,
        review_attribution=review_attribution,
        attribution_policy=attribution_policy,
        outputs=summary["outputs"],
        limit=max(int(getattr(args, "top", 5) or 5), 1),
    )
    summary["daily_brief"] = {
        "status": daily_brief.get("status", ""),
        "can_open_new_position": bool(daily_brief.get("can_open_new_position")),
        "allowed_order_count": int((daily_brief.get("counts") or {}).get("allowed_orders", 0) or 0),
        "blocked_order_count": int((daily_brief.get("counts") or {}).get("blocked_orders", 0) or 0),
        "must_handle_count": int((daily_brief.get("counts") or {}).get("must_handle", 0) or 0),
    }
    summary["steps"].append({"name": "workflow_gate", "status": workflow_gate["status"], "summary": workflow_gate})
    summary["steps"].append({"name": "trade_plan_batch", "status": trade_plan_batch.status, "summary": trade_plan_batch.to_dict()})
    summary["steps"].append({"name": "review_doctor", "status": review_doctor.get("status", "pass"), "summary": review_doctor})
    summary["steps"].append({"name": "execution_audit", "status": summary["execution_audit"]["status"], "summary": execution_audit})
    summary["steps"].append({"name": "review_attribution", "status": review_attribution.get("status", "pass"), "summary": review_attribution})
    summary["steps"].append({"name": "attribution_policy", "status": attribution_policy.get("status", "pass"), "summary": attribution_policy})
    summary["steps"].append({"name": "cockpit_gate", "status": cockpit.get("status", ""), "summary": cockpit})
    summary["status"] = _merge_workflow_status(
        summary["status"],
        workflow_gate.get("status", "pass"),
        trade_plan_batch.status,
        review_doctor.get("status", "pass"),
        cockpit.get("status", "pass"),
        timeline.get("status", "pass"),
        assistant.get("status", "pass"),
        summary["execution_audit"]["status"],
        review_attribution.get("status", "pass"),
        attribution_policy.get("status", "pass"),
        daily_brief.get("status", "pass"),
    )

    args.premarket_output.parent.mkdir(parents=True, exist_ok=True)
    args.premarket_output.write_text(_render_premarket_report_from_context(context) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "premarket_report", "status": "ok", "path": str(args.premarket_output)})

    args.battle_plan_output.parent.mkdir(parents=True, exist_ok=True)
    args.battle_plan_output.write_text(render_final_battle_plan_markdown(battle_plan) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "battle_plan_report", "status": "ok", "path": str(args.battle_plan_output)})

    args.cockpit_output.parent.mkdir(parents=True, exist_ok=True)
    args.cockpit_output.write_text(render_trading_cockpit_markdown(cockpit) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "cockpit_report", "status": "ok", "path": str(args.cockpit_output)})

    args.execution_audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.execution_audit_output.write_text(render_execution_audit_markdown(execution_audit) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "execution_audit_report", "status": "ok", "path": str(args.execution_audit_output)})

    args.lifecycle_output.parent.mkdir(parents=True, exist_ok=True)
    args.lifecycle_output.write_text(render_position_lifecycle_markdown(lifecycle_snapshot) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "lifecycle_report", "status": "ok", "path": str(args.lifecycle_output)})

    args.review_attribution_output.parent.mkdir(parents=True, exist_ok=True)
    args.review_attribution_output.write_text(render_review_attribution_markdown(review_attribution) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "review_attribution_report", "status": "ok", "path": str(args.review_attribution_output)})

    args.attribution_policy_output.parent.mkdir(parents=True, exist_ok=True)
    args.attribution_policy_output.write_text(render_attribution_policy_markdown(attribution_policy) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "attribution_policy_report", "status": "ok", "path": str(args.attribution_policy_output)})

    args.timeline_output.parent.mkdir(parents=True, exist_ok=True)
    args.timeline_output.write_text(render_trading_day_timeline_markdown(timeline) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "timeline_report", "status": "ok", "path": str(args.timeline_output)})
    if getattr(args, "record_state", False):
        summary["state"] = {
            "status": state.get("status", ""),
            "phase_count": state.get("phase_count", 0),
            "action_item_count": state.get("action_item_count", 0),
        }
        summary["steps"].append({"name": "trading_day_state", "status": "ok", "path": str(getattr(args, "state_log", ""))})

    args.assistant_output.parent.mkdir(parents=True, exist_ok=True)
    args.assistant_output.write_text(render_trading_assistant_markdown(assistant) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "assistant_report", "status": "ok", "path": str(args.assistant_output)})

    args.daily_output.parent.mkdir(parents=True, exist_ok=True)
    args.daily_output.write_text(render_daily_trade_brief_markdown(daily_brief) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "daily_brief_report", "status": "ok", "path": str(args.daily_output)})

    args.trade_plan_batch_output.parent.mkdir(parents=True, exist_ok=True)
    args.trade_plan_batch_output.write_text(render_trade_plan_batch_markdown(trade_plan_batch) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "trade_plan_batch_report", "status": "ok", "path": str(args.trade_plan_batch_output)})

    args.review_doctor_output.parent.mkdir(parents=True, exist_ok=True)
    args.review_doctor_output.write_text(render_review_doctor_markdown(review_doctor) + "\n", encoding="utf-8")
    summary["steps"].append({"name": "review_doctor_report", "status": "ok", "path": str(args.review_doctor_output)})

    if getattr(args, "record_actions", False):
        append_position_action_plan_record(args.action_log, context.get("holding_action_plan") or {})
        summary["steps"].append({"name": "holding_action_plan", "status": "ok", "path": str(args.action_log)})
    if getattr(args, "record_exit_plan", False):
        append_exit_plan_record(args.exit_log, context.get("exit_plan") or {})
        summary["steps"].append({"name": "exit_plan", "status": "ok", "path": str(args.exit_log)})
    if getattr(args, "record_discipline", False):
        _persist_discipline_from_args(
            args,
            "workflow.trading-day",
            gate_review=gate_review,
            trade_stats=context.get("trade_stats"),
            holding_risk=context.get("holding_risk"),
            allocation_plan=context.get("allocation_plan"),
        )
        summary["steps"].append({"name": "discipline_record", "status": "ok", "path": str(getattr(args, "discipline_log", ""))})

    _finish_workflow_summary(args, summary)


def _merge_workflow_status(current: str, *states: str) -> str:
    order = {"ok": 0, "pass": 0, "warn": 1, "block": 2, "fail": 3}
    result = current if current in order else "ok"
    for state in states:
        if order.get(state, 0) > order.get(result, 0):
            result = "fail" if state == "fail" else state
    return result


def _workflow_execution_gate(health: dict, repair_plan: dict, context: dict) -> dict:
    reasons: list[str] = []
    status = "pass"
    pretrade_checks = list(context.get("pretrade_checks", []) or [])
    pretrade_statuses = [str(item.get("status", "") or "") for item in pretrade_checks]
    holding_status = str((context.get("holding_risk") or {}).get("status", "pass") or "pass")
    holding_action_plan = context.get("holding_action_plan") or {}
    holding_action_status = str(holding_action_plan.get("status", "pass") or "pass")
    exit_plan = context.get("exit_plan") or {}
    exit_plan_status = str(exit_plan.get("status", "pass") or "pass")
    regime = str((context.get("market_temperature") or {}).get("regime", "") or "")
    battle_plan = context.get("final_battle_plan") or {}
    battle_plan_status = str(battle_plan.get("status", "") or "")
    battle_plan_reasons = list(battle_plan.get("reasons", []) or [])

    if health.get("status") == "fail":
        status = "block"
        reasons.append("Data health failed; do not continue the trading workflow.")
    if "block" in pretrade_statuses:
        status = "block"
        reasons.append("At least one pretrade check is blocking execution.")
    if holding_status == "block":
        status = "block"
        reasons.append("Holding risk is blocking new execution.")
    if holding_action_status == "block":
        status = "block"
        reasons.append("Holding action plan contains blocking tasks.")
    if exit_plan_status == "block":
        status = "block"
        reasons.append("Exit plan contains blocking sell tasks.")
    if regime in {"frozen", "empty"}:
        status = "block"
        reasons.append(f"Market regime blocks execution: {regime}")
    if battle_plan_status == "block":
        status = "block"
        reasons.append("Final battle plan blocks new execution.")
        reasons.extend(f"battle_plan: {item}" for item in battle_plan_reasons[:3])

    if status != "block":
        if health.get("status") == "warn":
            status = "warn"
            reasons.append("Data health has warning items.")
        if repair_plan.get("status") == "action_needed":
            status = "warn"
            reasons.append("Data repair plan needs action before relying on the workflow.")
        if "warn" in pretrade_statuses:
            status = "warn"
            reasons.append("At least one pretrade check is warning.")
        if holding_status == "warn":
            status = "warn"
            reasons.append("Holding risk has warning items.")
        if holding_action_status == "warn":
            status = "warn"
            reasons.append("Holding action plan has warning tasks.")
        if exit_plan_status == "warn":
            status = "warn"
            reasons.append("Exit plan has warning-level sell tasks.")
        if regime == "cold":
            status = "warn"
            reasons.append("Market regime is cold; reduce aggressiveness.")
        if battle_plan_status == "warn":
            status = "warn"
            reasons.append("Final battle plan is in warning mode.")
            reasons.extend(f"battle_plan: {item}" for item in battle_plan_reasons[:3])

    message = {
        "pass": "Workflow gate passed; trading tasks can proceed with normal manual checks.",
        "warn": "Workflow gate is warning; proceed only with reduced size and explicit review.",
        "block": "Workflow gate is blocking; 禁止新开仓 until blocking evidence is cleared.",
    }[status]
    return {
        "status": status,
        "message": message,
        "reasons": reasons,
        "pretrade_counts": {
            "pass": pretrade_statuses.count("pass"),
            "warn": pretrade_statuses.count("warn"),
            "block": pretrade_statuses.count("block"),
        },
        "holding_status": holding_status,
        "holding_action_status": holding_action_status,
        "exit_plan_status": exit_plan_status,
        "battle_plan_status": battle_plan_status,
        "holding_actions": {
            "exit_count": int(holding_action_plan.get("exit_count", 0) or 0),
            "reduce_count": int(holding_action_plan.get("reduce_count", 0) or 0),
            "watch_count": int(holding_action_plan.get("watch_count", 0) or 0),
        },
        "exit_plan": {
            "sell_all_count": int(exit_plan.get("sell_all_count", 0) or 0),
            "take_profit_count": int(exit_plan.get("take_profit_count", 0) or 0),
            "reduce_count": int(exit_plan.get("reduce_count", 0) or 0),
            "time_stop_count": int(exit_plan.get("time_stop_count", 0) or 0),
        },
        "market_regime": regime,
    }

def _finish_workflow_summary(args: argparse.Namespace, summary: dict) -> None:
    text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "summary_output", None):
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(text + "\n", encoding="utf-8")
    print(text)


def run_data_fetch_daily(args: argparse.Namespace) -> None:
    try:
        path = fetch_daily_to_cache(
            symbol=args.symbol,
            start_date=args.start,
            end_date=args.end,
            cache_dir=args.cache_dir,
            adjust=args.adjust,
            source=args.source,
        )
        print(json.dumps({"status": "ok", "path": str(path)}, ensure_ascii=False, indent=2))
    except Exception as exc:  # noqa: BLE001 - CLI should show structured provider failures.
        print(json.dumps({"status": "failed", "symbol": args.symbol, "error": str(exc)}, ensure_ascii=False, indent=2))

def run_data_fetch_batch(args: argparse.Namespace) -> None:
    summary = fetch_batch_summary(
        universe=args.universe,
        start=args.start,
        end=args.end or date.today().strftime("%Y%m%d"),
        adjust=args.adjust,
        cache_dir=args.cache_dir,
        manifest_path=args.manifest,
        source=args.source,
        limit=args.limit,
        refresh=args.refresh,
        refresh_stale_days=args.refresh_stale_days,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def fetch_batch_summary(
    *,
    universe: Path,
    start: str,
    end: str,
    adjust: str,
    cache_dir: Path,
    manifest_path: Path,
    source: str,
    limit: int | None = None,
    refresh: bool = False,
    refresh_stale_days: int | None = None,
) -> dict:
    stocks = read_universe(universe)
    if limit:
        stocks = stocks[:limit]

    manifest = CacheManifest(manifest_path)
    summary = {"ok": 0, "skipped": 0, "failed": 0, "by_provider": {}, "items": []}
    for stock in stocks:
        try:
            if not refresh:
                try:
                    cached = load_daily_cache(cache_dir, stock.symbol)
                except FileNotFoundError:
                    cached = None
                if cached is not None and not _cache_needs_refresh(cached, end, refresh_stale_days):
                    entry = CacheManifestEntry(
                        symbol=stock.symbol,
                        provider="cache",
                        path=str(cache_dir),
                        start=start,
                        end=end,
                        rows=len(cached),
                        status="skipped",
                    )
                    summary["skipped"] += 1
                    manifest.append(entry)
                    summary["items"].append(entry.__dict__)
                    continue
            result = fetch_with_fallback(
                symbol=stock.symbol,
                start=start,
                end=end,
                adjust=adjust,
                source=source,
            )
            path = save_daily_cache(cache_dir, stock.symbol, result.frame)
            entry = CacheManifestEntry(
                symbol=stock.symbol,
                provider=result.provider,
                path=str(path),
                start=start,
                end=end,
                rows=len(result.frame),
                status="ok",
            )
            summary["ok"] += 1
            summary["by_provider"][result.provider] = summary["by_provider"].get(result.provider, 0) + 1
        except Exception as exc:  # noqa: BLE001 - batch update should continue.
            entry = CacheManifestEntry(
                symbol=stock.symbol,
                provider=source,
                path="",
                start=start,
                end=end,
                rows=0,
                status="failed",
                error=str(exc),
            )
            summary["failed"] += 1
        manifest.append(entry)
        summary["items"].append(entry.__dict__)
    return summary


def _cache_needs_refresh(cached: pd.DataFrame, end: str, refresh_stale_days: int | None) -> bool:
    if refresh_stale_days is None:
        return False
    if cached.empty or "date" not in cached.columns:
        return True
    latest = pd.to_datetime(cached["date"]).max()
    if pd.isna(latest):
        return True
    end_date = pd.to_datetime(end)
    return int((end_date.normalize() - latest.normalize()).days) > refresh_stale_days

def run_data_health(args: argparse.Namespace) -> None:
    try:
        frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe, strict=args.strict)
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "rows": 0,
                    "symbols": 0,
                    "start_date": "",
                    "end_date": "",
                    "issues": [{"name": "missing_cache", "status": "fail", "message": str(exc)}],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    report = check_ohlcv_health(
        frame,
        min_rows_per_symbol=args.min_rows,
        max_stale_days=args.max_stale_days,
        as_of=args.as_of,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


def run_data_repair_plan(args: argparse.Namespace) -> None:
    try:
        frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe, strict=args.strict)
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "priority_symbols": [],
                    "refresh_candidates": [],
                    "backfill_candidates": [],
                    "monitor_only": {},
                    "recommended_steps": [str(exc)],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    plan = build_ohlcv_repair_plan(
        frame,
        min_rows_per_symbol=args.min_rows,
        max_stale_days=args.max_stale_days,
        as_of=args.as_of,
    )
    print(json.dumps(plan, ensure_ascii=False, indent=2))


def run_data_repair_execute(args: argparse.Namespace) -> None:
    try:
        frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe, strict=args.strict)
    except (FileNotFoundError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "mode": "dry-run" if not args.execute else "execute",
                    "targets": [],
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    plan = build_ohlcv_repair_plan(
        frame,
        min_rows_per_symbol=args.min_rows,
        max_stale_days=args.max_stale_days,
        as_of=args.as_of,
    )
    targets = list(plan.get("priority_symbols", []))
    if args.limit:
        targets = targets[: args.limit]
    start_date = args.start or str(plan.get("suggested_fetch_start", ""))
    end_date = args.end or str(plan.get("suggested_fetch_end", ""))

    summary = {
        "status": "ok" if targets else plan.get("status", "ok"),
        "mode": "execute" if args.execute else "dry-run",
        "target_count": len(targets),
        "targets": targets,
        "start": start_date,
        "end": end_date,
        "source": args.source,
        "items": [],
        "recommended_steps": plan.get("recommended_steps", []),
    }
    if not args.execute:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    for symbol in targets:
        try:
            path = fetch_daily_to_cache(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                cache_dir=args.cache_dir,
                adjust=args.adjust,
                source=args.source,
            )
            summary["items"].append({"symbol": symbol, "status": "ok", "path": str(path)})
        except Exception as exc:  # noqa: BLE001
            summary["status"] = "partial_failed"
            summary["items"].append({"symbol": symbol, "status": "failed", "error": str(exc)})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def run_data_db_init(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    store.init()
    print(json.dumps({"status": "ok", "path": str(args.db_path)}, ensure_ascii=False, indent=2))

def run_data_db_import_universe(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    store.init()
    if args.input:
        raw = pd.read_csv(args.input, dtype={"symbol": str, "code": str})
        filtered = filter_universe(
            raw,
            UniverseBuildOptions(
                include_st=args.include_st,
                include_bj=args.include_bj,
                include_star=not args.exclude_star,
                include_chinext=not args.exclude_chinext,
                min_list_days=args.min_list_days,
            ),
        )
    else:
        source = args.source if args.source != "auto" else source_from_args(args, "universe_source", "akshare")
        if source != "akshare":
            raise ValueError(f"Unsupported universe source: {source}")
        raw = fetch_akshare_universe_with_retry()
        filtered = filter_universe(
            raw,
            UniverseBuildOptions(
                include_st=args.include_st,
                include_bj=args.include_bj,
                include_star=not args.exclude_star,
                include_chinext=not args.exclude_chinext,
                min_list_days=args.min_list_days,
            ),
        )
    rows = store.upsert_universe(filtered)
    print(json.dumps({"status": "ok", "db_path": str(args.db_path), "rows": rows}, ensure_ascii=False, indent=2))

def run_data_db_import_daily(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    store.init()
    source = source_or_default(args, args.source, "daily_source", "auto")
    result = fetch_with_fallback(args.symbol, args.start, args.end, args.adjust, source=source)
    rows = store.upsert_daily_bars(result.frame, source=result.provider, adjust=args.adjust)
    store.log_fetch_job(args.symbol, args.start, args.end, result.provider, "ok", rows=rows)
    print(json.dumps({"status": "ok", "db_path": str(args.db_path), "provider": result.provider, "rows": rows}, ensure_ascii=False, indent=2))


def run_data_db_import_batch_daily(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    store.init()
    stocks = _stocks_for_db_batch(args, store)
    if args.limit:
        stocks = stocks[: args.limit]
    source = source_or_default(args, args.source, "daily_source", "auto")
    skipped = []
    if not getattr(args, "refresh", False):
        coverage = store.daily_coverage()
        requested_start = pd.to_datetime(args.start).strftime("%Y-%m-%d")
        requested_end = pd.to_datetime(args.end).strftime("%Y-%m-%d")
        pending = []
        for stock in stocks:
            symbol = str(stock["symbol"]).zfill(6)
            item = coverage.get(symbol)
            if item and _coverage_satisfies_request(item, requested_start, requested_end):
                skipped.append(symbol)
            else:
                pending.append(stock)
        stocks = pending
    workers = max(1, int(args.workers or 1))
    progress_every = max(0, int(args.progress_every or 0))
    summary = {
        "status": "ok",
        "db_path": str(args.db_path),
        "start": args.start,
        "end": args.end,
        "adjust": args.adjust,
        "source": source,
        "symbols": len(stocks),
        "skipped": len(skipped),
        "ok": 0,
        "failed": 0,
        "rows": 0,
        "by_provider": {},
        "failures": [],
    }
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(_fetch_daily_without_health, str(stock["symbol"]), args.start, args.end, args.adjust, source): stock
            for stock in stocks
        }
        for done, future in enumerate(as_completed(future_map), start=1):
            stock = future_map[future]
            symbol = str(stock["symbol"]).zfill(6)
            try:
                result = future.result()
                rows = store.upsert_daily_bars(result.frame, source=result.provider, adjust=args.adjust)
                store.log_fetch_job(symbol, args.start, args.end, result.provider, "ok", rows=rows)
                summary["ok"] += 1
                summary["rows"] += rows
                summary["by_provider"][result.provider] = summary["by_provider"].get(result.provider, 0) + 1
            except Exception as exc:  # noqa: BLE001 - keep the rest of the batch moving.
                summary["status"] = "partial_failed"
                summary["failed"] += 1
                error = str(exc)
                store.log_fetch_job(symbol, args.start, args.end, source, "failed", rows=0, error=error)
                if len(summary["failures"]) < 50:
                    summary["failures"].append({"symbol": symbol, "name": str(stock.get("name", "")), "error": error})
            if progress_every and (done == 1 or done % progress_every == 0 or done == len(stocks)):
                print(
                    json.dumps(
                        {
                            "event": "db_import_batch_daily_progress",
                            "done": done,
                            "total": len(stocks),
                            "ok": summary["ok"],
                            "failed": summary["failed"],
                            "rows": summary["rows"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def run_data_db_import_adjustment(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    store.init()
    provider = AkShareAdjustmentFactorProvider()
    symbol = str(args.symbol).zfill(6)
    frame = provider.fetch_adjustment_factors(symbol, args.start, args.end, adjust=args.adjust)
    rows = store.upsert_adjustment_factors(frame, source=f"{provider.name}:{args.adjust}")
    print(json.dumps({"status": "ok", "db_path": str(args.db_path), "symbol": symbol, "rows": rows, "provider": provider.name}, ensure_ascii=False, indent=2, default=str))


def run_data_db_import_batch_adjustment(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    store.init()
    stocks = _stocks_for_db_batch(args, store)
    if args.limit:
        stocks = stocks[: args.limit]
    if not getattr(args, "refresh", False):
        existing = _existing_adjustment_symbols(store)
        stocks = [stock for stock in stocks if str(stock["symbol"]).zfill(6) not in existing]
    provider = AkShareAdjustmentFactorProvider()
    workers = max(1, int(args.workers or 1))
    progress_every = max(0, int(args.progress_every or 0))
    summary = {
        "status": "ok",
        "db_path": str(args.db_path),
        "start": args.start,
        "end": args.end,
        "adjust": args.adjust,
        "symbols": len(stocks),
        "ok": 0,
        "empty": 0,
        "failed": 0,
        "rows": 0,
        "failures": [],
    }
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(provider.fetch_adjustment_factors, str(stock["symbol"]), args.start, args.end, args.adjust): stock
            for stock in stocks
        }
        for done, future in enumerate(as_completed(future_map), start=1):
            stock = future_map[future]
            symbol = str(stock["symbol"]).zfill(6)
            try:
                frame = future.result()
                rows = store.upsert_adjustment_factors(frame, source=f"{provider.name}:{args.adjust}")
                if rows:
                    summary["ok"] += 1
                    summary["rows"] += rows
                else:
                    summary["empty"] += 1
            except Exception as exc:  # noqa: BLE001 - keep the rest of the batch moving.
                summary["status"] = "partial_failed"
                summary["failed"] += 1
                if len(summary["failures"]) < 50:
                    summary["failures"].append({"symbol": symbol, "name": str(stock.get("name", "")), "error": str(exc)})
            if progress_every and (done == 1 or done % progress_every == 0 or done == len(stocks)):
                print(
                    json.dumps(
                        {
                            "event": "db_import_batch_adjustment_progress",
                            "done": done,
                            "total": len(stocks),
                            "ok": summary["ok"],
                            "empty": summary["empty"],
                            "failed": summary["failed"],
                            "rows": summary["rows"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def run_data_db_import_minute(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    store.init()
    symbol = str(args.symbol).zfill(6)
    source = getattr(args, "source", "auto")
    errors: list[str] = []
    try:
        provider_name = ""
        frame = pd.DataFrame()
        for provider in minute_provider_chain(source):
            try:
                frame = provider.fetch_minute(symbol, args.start, args.end, period=args.period, adjust=args.adjust)
                provider_name = provider.name
                break
            except Exception as exc:  # noqa: BLE001 - try the next minute source.
                errors.append(f"{provider.name}: {exc}")
        if frame.empty:
            raise RuntimeError("All minute providers failed: " + " | ".join(errors))
        path_without_suffix = _minute_cache_path(args.cache_dir, symbol, args.period, args.adjust, args.start, args.end)
        write_result = write_frame_cache(frame, path_without_suffix)
        record = {
            "symbol": symbol,
            "period": args.period,
            "start": args.start,
            "end": args.end,
            "adjust": args.adjust,
            "path": str(write_result.path),
            "rows": len(frame),
            "source": provider_name,
            "status": "ok",
            "error": "",
        }
        store.upsert_minute_bar_catalog(record)
        print(json.dumps({"status": "ok", "db_path": str(args.db_path), **record}, ensure_ascii=False, indent=2, default=str))
    except Exception as exc:  # noqa: BLE001 - catalog failed attempts for diagnosis.
        record = {
            "symbol": symbol,
            "period": args.period,
            "start": args.start,
            "end": args.end,
            "adjust": args.adjust,
            "path": "",
            "rows": 0,
            "source": source,
            "status": "failed",
            "error": str(exc),
        }
        store.upsert_minute_bar_catalog(record)
        print(json.dumps({"status": "failed", "db_path": str(args.db_path), **record}, ensure_ascii=False, indent=2, default=str))


def run_data_db_import_batch_minute(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    store.init()
    stocks = _stocks_for_db_batch(args, store)
    if args.limit:
        stocks = stocks[: args.limit]
    if not getattr(args, "refresh", False):
        existing = _existing_minute_catalog_keys(store)
        stocks = [
            stock for stock in stocks
            if (str(stock["symbol"]).zfill(6), str(args.period), str(args.start), str(args.end), str(args.adjust)) not in existing
        ]
    providers = minute_provider_chain(getattr(args, "source", "auto"))
    workers = max(1, int(args.workers or 1))
    progress_every = max(0, int(args.progress_every or 0))
    summary = {
        "status": "ok",
        "db_path": str(args.db_path),
        "start": args.start,
        "end": args.end,
        "period": args.period,
        "adjust": args.adjust,
        "symbols": len(stocks),
        "ok": 0,
        "failed": 0,
        "rows": 0,
        "failures": [],
    }
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(_fetch_and_cache_minute_chunk, providers, args.cache_dir, str(stock["symbol"]), args.start, args.end, args.period, args.adjust): stock
            for stock in stocks
        }
        for done, future in enumerate(as_completed(future_map), start=1):
            stock = future_map[future]
            symbol = str(stock["symbol"]).zfill(6)
            try:
                record = future.result()
                store.upsert_minute_bar_catalog(record)
                summary["ok"] += 1
                summary["rows"] += int(record.get("rows", 0) or 0)
            except Exception as exc:  # noqa: BLE001 - keep the rest of the batch moving.
                summary["status"] = "partial_failed"
                summary["failed"] += 1
                record = {
                    "symbol": symbol,
                    "period": args.period,
                    "start": args.start,
                    "end": args.end,
                    "adjust": args.adjust,
                    "path": "",
                    "rows": 0,
                    "source": getattr(args, "source", "auto"),
                    "status": "failed",
                    "error": str(exc),
                }
                store.upsert_minute_bar_catalog(record)
                if len(summary["failures"]) < 50:
                    summary["failures"].append({"symbol": symbol, "name": str(stock.get("name", "")), "error": str(exc)})
            if progress_every and (done == 1 or done % progress_every == 0 or done == len(stocks)):
                print(
                    json.dumps(
                        {
                            "event": "db_import_batch_minute_progress",
                            "done": done,
                            "total": len(stocks),
                            "ok": summary["ok"],
                            "failed": summary["failed"],
                            "rows": summary["rows"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def run_data_db_import_review(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    store.init()
    summary = {
        "status": "ok",
        "db_path": str(args.db_path),
        "items": [],
    }
    sources = [
        ("selections", getattr(args, "tracker", None), read_jsonl, store.insert_selections),
        ("trades", getattr(args, "journal", None), read_jsonl, store.insert_trade),
        ("promotions", getattr(args, "promotion_log", None), read_jsonl, store.insert_strategy_promotion),
        ("constraints", getattr(args, "constraint_log", None), read_jsonl, store.insert_strategy_constraint),
        ("discipline", getattr(args, "discipline_log", None), read_jsonl, store.insert_discipline_record),
        ("trade_plans", getattr(args, "trade_plan_log", None), read_jsonl, store.insert_trade_plan),
        ("execution_confirmations", getattr(args, "confirm_log", None), read_jsonl, store.insert_execution_confirmation),
        ("action_plans", getattr(args, "action_log", None), read_jsonl, store.insert_position_action_plan),
        ("exit_plans", getattr(args, "exit_log", None), read_jsonl, store.insert_exit_plan),
        ("lifecycle_snapshots", getattr(args, "lifecycle_log", None), read_jsonl, store.insert_lifecycle_snapshot),
        ("trading_day_states", getattr(args, "state_log", None), read_jsonl, store.insert_trading_day_state),
        ("order_approvals", getattr(args, "approval_log", None), read_jsonl, store.insert_order_approval),
    ]
    for name, path, reader, writer in sources:
        if not path or not path.exists():
            summary["items"].append({"name": name, "status": "missing"})
            continue
        records = reader(path)
        if not records:
            summary["items"].append({"name": name, "status": "empty", "path": str(path)})
            continue
        existing = _existing_fingerprints_for_review_source(store, name)
        imported = 0
        skipped = 0
        if name == "selections":
            payloads = _dedupe_review_records(records, existing)
            imported = len(payloads)
            skipped = len(records) - imported
            if payloads:
                writer(payloads)
        elif name == "trades":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record)
                imported += 1
        elif name == "promotions":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record)
                imported += 1
        elif name == "constraints":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record)
                imported += 1
        elif name == "discipline":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record)
                imported += 1
        elif name == "trade_plans":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record)
                imported += 1
        elif name == "execution_confirmations":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record)
                imported += 1
        elif name == "action_plans":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record)
                imported += 1
        elif name == "exit_plans":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record)
                imported += 1
        elif name == "lifecycle_snapshots":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record, snapshot_date=str(record.get("snapshot_date", "")))
                imported += 1
        elif name == "trading_day_states":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record)
                imported += 1
        elif name == "order_approvals":
            for record in records:
                if _record_fingerprint(record) in existing:
                    skipped += 1
                    continue
                writer(record)
                imported += 1
        summary["items"].append({"name": name, "status": "ok", "imported": imported, "skipped": skipped, "path": str(path)})
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))

def run_data_db_screen(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    universe = store.read_universe()
    if universe.empty:
        raise FileNotFoundError("Universe table is empty. Import a universe first.")
    frame = store.read_daily_bars()
    if frame.empty:
        raise FileNotFoundError("Daily bars table is empty. Import daily bars first.")
    frame = frame.merge(universe, on="symbol", how="left")
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=_current_strategy_health(args),
    )
    print(json.dumps(candidates.to_dict(orient="records"), ensure_ascii=False, indent=2, default=str))

def run_data_db_health(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    frame = store.read_daily_bars()
    if frame.empty:
        print(json.dumps({"status": "fail", "rows": 0, "symbols": 0, "issues": [{"name": "empty", "status": "fail", "message": "Database daily_bars table is empty."}]}, ensure_ascii=False, indent=2))
        return
    report = check_ohlcv_health(frame, min_rows_per_symbol=args.min_rows, max_stale_days=args.max_stale_days, as_of=args.as_of)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


def run_data_db_doctor(args: argparse.Namespace) -> None:
    summary = build_review_doctor_report(
        selections=_sqlite_selection_records(args.db_path),
        trades=_sqlite_trade_records(args.db_path),
        trade_plans=_sqlite_trade_plan_records(args.db_path),
        execution_confirmations=_sqlite_execution_confirmation_records(args.db_path),
        action_plans=_sqlite_position_action_records(args.db_path),
        exit_plans=_sqlite_exit_plan_records(args.db_path),
        lifecycle_snapshots=_sqlite_lifecycle_snapshot_records(args.db_path),
        trading_day_states=_sqlite_trading_day_state_records(args.db_path),
    )
    text = render_review_doctor_markdown(summary) if getattr(args, "format", "json") == "markdown" else json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)

def run_data_db_catalog(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    catalog = store.market_catalog()
    catalog["db_path"] = str(args.db_path)
    if getattr(args, "format", "json") == "markdown":
        lines = [
            "# Market Data Catalog",
            "",
            f"- DB: `{args.db_path}`",
            f"- Universe: {catalog['universe']['rows']} symbols",
            f"- Daily bars: {catalog['daily_bars']['rows']} rows / {catalog['daily_bars']['symbols']} symbols / {catalog['daily_bars']['start']} to {catalog['daily_bars']['end']}",
            f"- Adjustment factors: {catalog['adjustment_factors']['rows']} rows / {catalog['adjustment_factors']['symbols']} symbols",
            f"- Minute catalog: {catalog['minute_bars']['catalog_jobs']} jobs / {catalog['minute_bars']['rows']} rows / {catalog['minute_bars']['symbols']} symbols",
            f"- Fetch jobs: {catalog['fetch_jobs']['total']} total / {catalog['fetch_jobs']['ok']} ok / {catalog['fetch_jobs']['failed']} failed",
        ]
        print("\n".join(lines))
        return
    print(json.dumps(catalog, ensure_ascii=False, indent=2, default=str))


def _stocks_for_db_batch(args: argparse.Namespace, store: SQLiteStore) -> list[dict[str, Any]]:
    if getattr(args, "universe", None):
        return [stock.__dict__ for stock in read_universe(args.universe)]
    universe = store.read_universe()
    if universe.empty:
        raw = fetch_akshare_universe_with_retry()
        universe = filter_universe(
            raw,
            UniverseBuildOptions(include_st=args.include_st, include_bj=args.include_bj),
        )
        store.upsert_universe(universe)
    return universe.to_dict(orient="records")


def _fetch_daily_without_health(symbol: str, start: str, end: str, adjust: str, source: str) -> ProviderResult:
    errors: list[str] = []
    for provider in provider_chain(source):
        try:
            frame = provider.fetch_daily(symbol=symbol, start=start, end=end, adjust=adjust)
            if not frame.empty:
                return ProviderResult(provider=provider.name, frame=frame)
            errors.append(f"{provider.name}: empty result")
        except Exception as exc:  # noqa: BLE001 - try the next configured source.
            errors.append(f"{provider.name}: {exc}")
    raise RuntimeError("All data providers failed: " + " | ".join(errors))


def _coverage_satisfies_request(item: dict[str, Any], requested_start: str, requested_end: str) -> bool:
    if not item.get("start") or not item.get("end"):
        return False
    start_gap = (pd.to_datetime(item["start"]) - pd.to_datetime(requested_start)).days
    end_gap = (pd.to_datetime(requested_end) - pd.to_datetime(item["end"])).days
    start_ok = item["start"] <= requested_start or 0 <= start_gap <= 10
    end_ok = item["end"] >= requested_end or 0 <= end_gap <= 10
    if start_ok and end_ok:
        return True
    if not end_ok or start_gap <= 10:
        return False
    rows = int(item.get("rows", 0) or 0)
    observed_days = max(1, (pd.to_datetime(item["end"]) - pd.to_datetime(item["start"])).days + 1)
    observed_density = rows / observed_days
    return bool(rows >= 30 and observed_density >= 0.35)


def _minute_cache_path(cache_dir: Path, symbol: str, period: str, adjust: str, start: str, end: str) -> Path:
    start_label = pd.to_datetime(start).strftime("%Y%m%d%H%M%S")
    end_label = pd.to_datetime(end).strftime("%Y%m%d%H%M%S")
    adjust_label = adjust or "raw"
    return cache_dir / f"period={period}" / f"adjust={adjust_label}" / str(symbol).zfill(6) / f"{start_label}_{end_label}"


def _existing_adjustment_symbols(store: SQLiteStore) -> set[str]:
    with store.connect() as conn:
        rows = conn.execute("SELECT DISTINCT symbol FROM adjustment_factors").fetchall()
    return {str(row["symbol"]).zfill(6) for row in rows}


def _existing_minute_catalog_keys(store: SQLiteStore) -> set[tuple[str, str, str, str, str]]:
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT symbol, period, start, end, adjust
            FROM minute_bar_catalog
            WHERE status = 'ok'
            """
        ).fetchall()
    return {
        (str(row["symbol"]).zfill(6), str(row["period"]), str(row["start"]), str(row["end"]), str(row["adjust"]))
        for row in rows
    }


def _fetch_and_cache_minute_chunk(
    providers: list[Any],
    cache_dir: Path,
    symbol: str,
    start: str,
    end: str,
    period: str,
    adjust: str,
) -> dict[str, Any]:
    normalized_symbol = str(symbol).zfill(6)
    errors: list[str] = []
    provider_name = ""
    frame = pd.DataFrame()
    for provider in providers:
        try:
            frame = provider.fetch_minute(normalized_symbol, start, end, period=period, adjust=adjust)
            provider_name = provider.name
            break
        except Exception as exc:  # noqa: BLE001 - try the next minute source.
            errors.append(f"{provider.name}: {exc}")
    if frame.empty:
        raise RuntimeError("All minute providers failed: " + " | ".join(errors))
    path_without_suffix = _minute_cache_path(cache_dir, normalized_symbol, period, adjust, start, end)
    write_result = write_frame_cache(frame, path_without_suffix)
    record = {
        "symbol": normalized_symbol,
        "period": period,
        "start": start,
        "end": end,
        "adjust": adjust,
        "path": str(write_result.path),
        "rows": len(frame),
        "source": provider_name,
        "status": "ok",
        "error": "",
    }
    return record

def run_data_universe(args: argparse.Namespace) -> None:
    try:
        status = "ok"
        fallback_error = ""
        if args.input:
            raw = pd.read_csv(args.input, dtype={"symbol": str, "code": str})
        else:
            source = source_or_default(args, args.source, "universe_source", "akshare")
            if source != "akshare":
                raise ValueError(f"Unsupported universe source: {source}")
            try:
                raw = fetch_akshare_universe_with_retry()
            except Exception as exc:
                if not args.output.exists():
                    raise
                raw = pd.read_csv(args.output, dtype={"symbol": str, "code": str})
                status = "fallback_cached"
                fallback_error = str(exc)
        filtered = filter_universe(
            raw,
            UniverseBuildOptions(
                include_st=args.include_st,
                include_bj=args.include_bj,
                include_star=not args.exclude_star,
                include_chinext=not args.exclude_chinext,
                min_list_days=args.min_list_days,
            ),
        )
        path = save_universe(filtered, args.output)
        print(
            json.dumps(
                {
                    "status": status,
                    "path": str(path),
                    "rows": len(filtered),
                    "markets": filtered["market"].value_counts().to_dict(),
                    "boards": filtered["board"].value_counts().to_dict(),
                    "fallback_error": fallback_error,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as exc:  # noqa: BLE001 - data source failures should be structured.
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))


def run_data_table(args: argparse.Namespace) -> None:
    payload = fetch_table_with_fallback(source=args.source, **args.query)
    print(json.dumps({"provider": payload.provider, "rows": len(payload.frame), "data": payload.frame.to_dict(orient="records")}, ensure_ascii=False, indent=2, default=str))


def run_data_provider_health(args: argparse.Namespace) -> None:
    store = ProviderHealthStore(Path("data/provider_health.json"))
    records = store.read()
    payload = [
        {
            "name": record.name,
            "success": record.success,
            "failure": record.failure,
            "score": round(record.score, 3),
            "last_error": record.last_error,
        }
        for record in sorted(records.values(), key=lambda item: item.score, reverse=True)
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))

def run_review_selections(args: argparse.Namespace) -> None:
    horizons = tuple(int(item.strip()) for item in args.horizons.split(",") if item.strip())
    if getattr(args, "sqlite", None):
        selections = _sqlite_selection_records(args.sqlite)
        frame = read_ohlcv_csv(args.csv)
        results = pd.DataFrame([result.to_dict() for result in validate_selections(selections, frame, horizons=horizons)])
    else:
        results = validate_selection_file(args.tracker, args.csv, horizons=horizons)
    summary = summarize_forward_returns(results)
    print(
        json.dumps(
            {
                "summary": summary.to_dict(orient="records"),
                "details": results.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

def run_review_trade_add(args: argparse.Namespace) -> None:
    tags = [item.strip() for item in args.tags.split(",") if item.strip()]
    gate = _gate_context_from_trade_args(args)
    trade_plan = _trade_plan_from_args(args)
    execution_confirm = _execution_confirmation_from_args(args)
    order_approval = _order_approval_from_args(args)
    exception_reason = str((trade_plan or {}).get("exception_reason", getattr(args, "exception_reason", "")) or "").strip()
    forced_exception_reasons = _forced_trade_exception_reasons(
        side=args.side,
        quantity=args.quantity,
        price=args.price,
        gate=gate,
        trade_plan=trade_plan,
        execution_confirm=execution_confirm,
        order_approval=order_approval,
    )
    discipline_exception = bool(
        (trade_plan or {}).get("discipline_exception", getattr(args, "discipline_exception", False))
        or forced_exception_reasons
    )
    if trade_plan:
        tags.extend(_trade_plan_tags(trade_plan))
    if execution_confirm:
        tags.extend(_execution_confirm_tags(execution_confirm))
    if order_approval:
        tags.extend(_order_approval_tags(order_approval))
    if gate.get("status") in {"warn", "block"}:
        tag = f"gate-{gate['status']}"
        if tag not in tags:
            tags.append(tag)
    if discipline_exception and "discipline-exception" not in tags:
        tags.append("discipline-exception")
    if discipline_exception and not exception_reason and "exception-missing-reason" not in tags:
        tags.append("exception-missing-reason")
    if execution_confirm and str(execution_confirm.get("status", "") or "") == "block" and "confirm-violated" not in tags:
        tags.append("confirm-violated")
    if order_approval and str(order_approval.get("status", "") or "") == "block" and "approval-violated" not in tags:
        tags.append("approval-violated")
    if forced_exception_reasons:
        tags.extend(reason for reason in forced_exception_reasons if reason not in tags)
    tags = _dedupe_text(tags)
    actual_pct = args.actual_pct
    if order_approval and not actual_pct:
        actual_pct = float(order_approval.get("confirmed_pct", 0) or 0)
    elif execution_confirm and not actual_pct:
        actual_pct = float(execution_confirm.get("confirmed_pct", 0) or 0)
    entry = TradeJournalEntry(
        date=args.date,
        symbol=str(args.symbol).zfill(6),
        side=args.side.upper(),
        price=args.price,
        quantity=args.quantity,
        reason=args.reason,
        name=args.name or _trade_plan_text(trade_plan, "name") or _execution_confirm_name(execution_confirm),
        strategy=args.strategy or _trade_plan_text(trade_plan, "strategy"),
        market_regime=args.market_regime,
        planned_pct=_execution_confirm_number(execution_confirm, "confirmed_pct", _trade_plan_number(trade_plan, "planned_pct", args.planned_pct)),
        actual_pct=actual_pct,
        planned_price=_execution_confirm_number(execution_confirm, "current_price", _trade_plan_number(trade_plan, "entry_price", args.planned_price)),
        stop_price=_execution_confirm_nested_number(execution_confirm, "pretrade_result", "stop_price", _trade_plan_number(trade_plan, "stop_price", args.stop_price)),
        target_price=_execution_confirm_nested_number(execution_confirm, "pretrade_result", "target_price", _trade_plan_number(trade_plan, "target_price", args.target_price)),
        tags=tags,
        mistake_type=args.mistake_type,
        review=args.review,
        gate_status=str((trade_plan or {}).get("gate_status", gate.get("status", _execution_confirm_text(execution_confirm, "final_gate_status")))),
        gate_message=str((trade_plan or {}).get("gate_reason", gate.get("message", _execution_confirm_text(execution_confirm, "decision")))),
        gate_reasons=_dedupe_text(list(gate.get("reasons", []) or _execution_confirm_reasons(execution_confirm)) + forced_exception_reasons),
        workflow_summary=str(getattr(args, "workflow_summary", "") or ""),
        discipline_exception=discipline_exception,
        exception_reason=exception_reason,
        execution_confirmation_path=str(getattr(args, "execution_confirm", "") or ""),
        execution_confirmation_created_at=_execution_confirm_text(execution_confirm, "created_at"),
        execution_confirmation_status=_execution_confirm_text(execution_confirm, "status"),
        execution_confirmation_decision=_execution_confirm_text(execution_confirm, "decision"),
        confirmation_price=_execution_confirm_optional_number(execution_confirm, "current_price"),
        confirmation_reference_price=_execution_confirm_optional_number(execution_confirm, "reference_price"),
        confirmed_pct=_execution_confirm_number(execution_confirm, "confirmed_pct", 0.0),
        confirmed_value=_execution_confirm_number(execution_confirm, "confirmed_value", 0.0),
        suggested_quantity=int(_execution_confirm_number(execution_confirm, "suggested_quantity", 0) or 0),
        confirmation_price_deviation_pct=_trade_vs_confirm_price_gap(execution_confirm, args.price),
        order_approval_path=str(getattr(args, "order_approval", "") or ""),
        order_approval_created_at=_order_approval_text(order_approval, "created_at"),
        order_approval_status=_order_approval_text(order_approval, "status"),
        order_approval_decision=_order_approval_text(order_approval, "decision"),
        approved_pct=_order_approval_number(order_approval, "confirmed_pct", 0.0),
        approved_value=_order_approval_number(order_approval, "confirmed_value", 0.0),
        approved_quantity=int(_order_approval_number(order_approval, "suggested_quantity", 0) or 0),
    )
    TradeJournal(args.journal, sqlite_path=getattr(args, "sqlite", None)).add(entry)
    print(json.dumps(entry.to_record(), ensure_ascii=False, indent=2))


def _forced_trade_exception_reasons(
    *,
    side: str,
    quantity: int,
    price: float,
    gate: dict,
    trade_plan: dict | None,
    execution_confirm: dict | None,
    order_approval: dict | None,
) -> list[str]:
    if str(side or "").upper() != "BUY":
        return []
    reasons: list[str] = []
    gate_status = str((trade_plan or {}).get("gate_status", gate.get("status", "")) or "")
    if gate_status in {"warn", "block"}:
        reasons.append(f"forced-gate-{gate_status}")

    confirm_status = str((execution_confirm or {}).get("status", "") or "")
    if confirm_status == "block":
        reasons.append("forced-confirm-block")
    confirm_quantity = int((execution_confirm or {}).get("suggested_quantity", 0) or 0)
    if execution_confirm and confirm_quantity <= 0 and int(quantity or 0) > 0:
        reasons.append("forced-confirm-no-quantity")
    if confirm_quantity > 0 and int(quantity or 0) > confirm_quantity:
        reasons.append("forced-confirm-size-exceeded")
    confirm_price = _execution_confirm_optional_number(execution_confirm, "current_price")
    if confirm_price not in (None, 0) and float(price) / float(confirm_price) - 1.0 > 0.005:
        reasons.append("forced-confirm-price-chase")

    approval_status = str((order_approval or {}).get("status", "") or "")
    if approval_status == "block":
        reasons.append("forced-approval-block")
    approved_quantity = int((order_approval or {}).get("suggested_quantity", 0) or 0)
    if order_approval and approved_quantity <= 0 and int(quantity or 0) > 0:
        reasons.append("forced-approval-no-quantity")
    if approved_quantity > 0 and int(quantity or 0) > approved_quantity:
        reasons.append("forced-approval-size-exceeded")
    return _dedupe_text(reasons)


def _dedupe_text(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _gate_context_from_trade_args(args: argparse.Namespace) -> dict:
    gate: dict = {}
    workflow_summary = getattr(args, "workflow_summary", None)
    if workflow_summary and workflow_summary.exists():
        payload = json.loads(workflow_summary.read_text(encoding="utf-8"))
        gate = dict(payload.get("gate") or {})
    if getattr(args, "gate_status", ""):
        gate["status"] = args.gate_status
    if getattr(args, "gate_message", ""):
        gate["message"] = args.gate_message
    reasons = list(getattr(args, "gate_reason", []) or [])
    if reasons:
        gate["reasons"] = reasons
    return gate

def run_review_trade_list(args: argparse.Namespace) -> None:
    records = _trade_records_from_args(args)
    print(json.dumps(records, ensure_ascii=False, indent=2, default=str))

def run_review_trade_stats(args: argparse.Namespace) -> None:
    records = _trade_records_from_args(args)
    print(json.dumps(summarize_trade_journal(records), ensure_ascii=False, indent=2))


def run_review_gates(args: argparse.Namespace) -> None:
    records = _filter_gate_records(
        _trade_records_from_args(args),
        strategy=getattr(args, "strategy", ""),
        symbol=getattr(args, "symbol", ""),
    )
    summary = summarize_gate_journal(records, limit=getattr(args, "limit", 20))
    if getattr(args, "format", "json") == "markdown":
        text = render_gate_review_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_exceptions(args: argparse.Namespace) -> None:
    summary = summarize_discipline_exceptions(_trade_records_from_args(args), limit=getattr(args, "limit", 20))
    if getattr(args, "format", "json") == "markdown":
        text = render_discipline_exception_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_trade_plan(args: argparse.Namespace) -> None:
    records = _trade_plan_records_from_args(args)
    summary = summarize_trade_plan_records(records, limit=getattr(args, "limit", 20))
    if getattr(args, "format", "json") == "markdown":
        text = render_trade_plan_summary_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_trade_audit(args: argparse.Namespace) -> None:
    plan_records = _trade_plan_records_from_args(args)
    trade_records = _trade_records_from_args(args)
    summary = summarize_trade_plan_audit(plan_records, trade_records, limit=getattr(args, "limit", 20))
    if getattr(args, "format", "json") == "markdown":
        text = render_trade_plan_audit_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_execution_audit(args: argparse.Namespace) -> None:
    summary = summarize_execution_audit(
        _execution_confirmation_records_from_args(args),
        _trade_records_from_args(args),
        lookahead_days=getattr(args, "lookahead_days", 1),
        limit=getattr(args, "limit", 20),
    )
    if getattr(args, "format", "json") == "markdown":
        text = render_execution_audit_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_approval_audit(args: argparse.Namespace) -> None:
    summary = summarize_approval_execution(
        _order_approval_records_from_args(args),
        _trade_records_from_args(args),
        lookahead_days=getattr(args, "lookahead_days", 1),
        value_tolerance_pct=getattr(args, "value_tolerance_pct", 0.02),
        limit=getattr(args, "limit", 20),
    )
    if getattr(args, "format", "json") == "markdown":
        text = render_approval_execution_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_approval_cooldown(args: argparse.Namespace) -> None:
    audit_summary = summarize_approval_execution(
        _order_approval_records_from_args(args),
        _trade_records_from_args(args),
        lookahead_days=getattr(args, "lookahead_days", 1),
        value_tolerance_pct=getattr(args, "value_tolerance_pct", 0.02),
        limit=getattr(args, "limit", 20),
    )
    constraints = build_approval_cooldown_constraints(
        audit_summary,
        block_threshold=getattr(args, "block_threshold", 1),
        warn_threshold=getattr(args, "warn_threshold", 2),
        fallback_threshold=getattr(args, "fallback_threshold", 2),
        warn_exposure_multiplier=getattr(args, "warn_exposure_multiplier", 0.5),
    )
    if getattr(args, "record", False):
        for record in constraints:
            persist_constraint_audit(
                record,
                log_path=getattr(args, "constraint_log", None),
                sqlite_path=getattr(args, "sqlite", None),
            )
    payload = summarize_approval_cooldown(constraints)
    payload["approval_audit"] = audit_summary
    if getattr(args, "format", "json") == "markdown":
        text = render_approval_cooldown_markdown(payload)
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_attribution(args: argparse.Namespace) -> None:
    summary = _review_attribution_report_from_args(args)
    if getattr(args, "format", "json") == "markdown":
        text = render_review_attribution_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_attribution_policy(args: argparse.Namespace) -> None:
    attribution = _review_attribution_report_from_args(args)
    policy = build_attribution_policy(
        attribution,
        default_strategy=getattr(args, "default_strategy", "") or getattr(args, "strategy", "") or "manual_order",
        effective_date=getattr(args, "effective_date", "") or getattr(args, "attribution_policy_date", ""),
        warn_exposure_multiplier=getattr(args, "warn_exposure_multiplier", 0.5),
    )
    if getattr(args, "record", False):
        _persist_attribution_policy(args, policy)
    if getattr(args, "format", "json") == "markdown":
        text = render_attribution_policy_markdown(policy)
    else:
        text = json.dumps(policy, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def _review_attribution_report_from_args(args: argparse.Namespace) -> dict:
    trade_records = _trade_records_from_args(args)
    plan_records = _trade_plan_records_from_args(args)
    execution_records = _execution_confirmation_records_from_args(args)
    approval_records = _order_approval_records_from_args(args)
    trade_plan_audit = summarize_trade_plan_audit(plan_records, trade_records, limit=getattr(args, "limit", 12))
    execution_audit = summarize_execution_audit(
        execution_records,
        trade_records,
        lookahead_days=getattr(args, "lookahead_days", 1),
        limit=getattr(args, "limit", 12),
    )
    approval_audit = summarize_approval_execution(
        approval_records,
        trade_records,
        lookahead_days=getattr(args, "lookahead_days", 1),
        value_tolerance_pct=getattr(args, "value_tolerance_pct", 0.02),
        limit=getattr(args, "limit", 12),
    )
    approval_cooldown = summarize_approval_cooldown(
        build_approval_cooldown_constraints(
            approval_audit,
            block_threshold=getattr(args, "block_threshold", 1),
            warn_threshold=getattr(args, "warn_threshold", 2),
            fallback_threshold=getattr(args, "fallback_threshold", 2),
            warn_exposure_multiplier=getattr(args, "warn_exposure_multiplier", 0.5),
        )
    )
    gate_review = summarize_gate_journal(trade_records, limit=getattr(args, "limit", 12))
    trade_stats = summarize_trade_journal(trade_records)
    lifecycle_snapshot = _latest_review_lifecycle_snapshot_from_args(args, limit=getattr(args, "limit", 12))
    return build_review_attribution_report(
        trade_plan_audit=trade_plan_audit,
        execution_audit=execution_audit,
        approval_audit=approval_audit,
        approval_cooldown=approval_cooldown,
        gate_review=gate_review,
        trade_stats=trade_stats,
        lifecycle_snapshot=lifecycle_snapshot,
        limit=getattr(args, "limit", 12),
    )


def run_review_action_execution(args: argparse.Namespace) -> None:
    action_records = _position_action_records_from_args(args)
    trade_records = _trade_records_from_args(args)
    summary = summarize_action_execution(
        action_records,
        trade_records,
        lookahead_days=getattr(args, "lookahead_days", 3),
        limit=getattr(args, "limit", 20),
    )
    if getattr(args, "format", "json") == "markdown":
        text = render_action_execution_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_exit_audit(args: argparse.Namespace) -> None:
    exit_records = _exit_plan_records_from_args(args)
    trade_records = _trade_records_from_args(args)
    summary = summarize_exit_execution(
        exit_records,
        trade_records,
        lookahead_days=getattr(args, "lookahead_days", 3),
        limit=getattr(args, "limit", 20),
    )
    if getattr(args, "format", "json") == "markdown":
        text = render_exit_execution_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_lot_stats(args: argparse.Namespace) -> None:
    prices = parse_price_overrides(getattr(args, "price", []) or [])
    records = _trade_records_from_args(args)
    book = build_lot_book(records, prices=prices, as_of=getattr(args, "as_of", None))
    text = render_lot_book_markdown(book) if getattr(args, "format", "json") == "markdown" else json.dumps(book.to_dict(), ensure_ascii=False, indent=2)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_lot_exit_audit(args: argparse.Namespace) -> None:
    exit_records = _exit_plan_records_from_args(args)
    trade_records = _trade_records_from_args(args)
    summary = summarize_lot_exit_execution(
        exit_records,
        trade_records,
        lookahead_days=getattr(args, "lookahead_days", 3),
        limit=getattr(args, "limit", 20),
    )
    if getattr(args, "format", "json") == "markdown":
        text = render_lot_exit_execution_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_lifecycle(args: argparse.Namespace) -> None:
    snapshot = _position_lifecycle_snapshot_from_args(args, limit=getattr(args, "limit", 20))
    text = render_position_lifecycle_markdown(snapshot) if getattr(args, "format", "json") == "markdown" else json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_lifecycle_history(args: argparse.Namespace) -> None:
    summary = build_review_history(
        trade_plans=_trade_plan_records_from_args(args),
        trades=_trade_records_from_args(args),
        action_plans=_position_action_records_from_args(args),
        exit_plans=_exit_plan_records_from_args(args),
        lifecycle_snapshots=_lifecycle_snapshot_records_from_args(args),
        limit=getattr(args, "limit", 20),
    )
    text = render_review_history_markdown(summary) if getattr(args, "format", "json") == "markdown" else json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_timeline_history(args: argparse.Namespace) -> None:
    records = _trading_day_state_records_from_args(args)
    summary = summarize_trading_day_state_records(records, limit=getattr(args, "limit", 20))
    text = render_trading_day_state_history_markdown(summary) if getattr(args, "format", "json") == "markdown" else json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_timeline_watch(args: argparse.Namespace) -> None:
    records = _trading_day_state_records_from_args(args)
    report = build_trading_day_watchdog(
        records,
        as_of=getattr(args, "as_of", None),
        repeat_threshold=getattr(args, "repeat_threshold", 2),
        stale_days=getattr(args, "stale_days", 1),
        limit=getattr(args, "limit", 20),
    )
    text = render_trading_day_watchdog_markdown(report) if getattr(args, "format", "json") == "markdown" else json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_doctor(args: argparse.Namespace) -> None:
    report = _review_doctor_from_args(
        args,
        lifecycle_snapshots=_merge_lifecycle_snapshots(
            _lifecycle_snapshot_records_from_args(args),
            _position_lifecycle_snapshot_from_args(args, limit=getattr(args, "limit", 20)),
        ),
    )
    text = (
        render_review_doctor_markdown(report)
        if getattr(args, "format", "json") == "markdown"
        else json.dumps(report, ensure_ascii=False, indent=2, default=str)
    )
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_review_approvals(args: argparse.Namespace) -> None:
    records = _order_approval_records_from_args(args)
    symbol = str(getattr(args, "symbol", "") or "").strip()
    status = str(getattr(args, "status", "") or "").strip()
    if symbol:
        normalized = symbol.zfill(6)
        records = [record for record in records if str(record.get("symbol", "")).zfill(6) == normalized]
    if status:
        records = [record for record in records if str(record.get("status", "") or "") == status]
    summary = summarize_order_approvals(records, limit=getattr(args, "limit", 20))
    text = (
        render_order_approval_summary_markdown(summary)
        if getattr(args, "format", "json") == "markdown"
        else json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    )
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_portfolio_plan(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    current_strategy_health = _current_strategy_health(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=current_strategy_health,
    )
    temperature = calculate_market_temperature(frame, candidates).to_dict()
    allocation_plan = build_allocation_plan(
        candidates,
        temperature,
        cash=args.cash,
        max_positions=args.top,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=current_strategy_health,
    )
    result = run_pretrade_check(
        candidates,
        temperature,
        symbol=args.symbol,
        entry_price=args.entry_price,
        planned_pct=args.planned_pct,
        cash=args.cash,
        stop_price=args.stop_price,
        target_price=args.target_price,
        max_positions=args.top,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=current_strategy_health,
    )
    plan = build_trade_plan(
        symbol=args.symbol,
        trade_date=getattr(args, "trade_date", None),
        pretrade_result=result,
        allocation_plan=allocation_plan,
        discipline_exception=bool(getattr(args, "discipline_exception", False)),
        exception_reason=str(getattr(args, "exception_reason", "") or ""),
    )
    persist_constraint_audit(
        build_constraint_audit_record("portfolio.plan", plan.strategy_constraint),
        log_path=getattr(args, "constraint_log", None),
        sqlite_path=getattr(args, "sqlite", None),
    )
    payload = plan.to_dict()
    if getattr(args, "record", False):
        append_trade_plan_record(
            getattr(args, "log", Path("data/review/trade_plans.jsonl")),
            payload,
            sqlite_path=getattr(args, "sqlite", None),
        )
    rendered = render_trade_plan_markdown(plan) if getattr(args, "format", "json") == "markdown" else json.dumps(payload, ensure_ascii=False, indent=2)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(rendered)


def run_portfolio_plan_batch(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    strategy_health = _current_strategy_health(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=strategy_health,
    )
    temperature = calculate_market_temperature(frame, candidates).to_dict()
    batch = build_trade_plan_batch(
        candidates=candidates,
        market_temperature=temperature,
        cash=args.cash,
        max_positions=args.top,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=strategy_health,
        trade_date=getattr(args, "trade_date", None),
        discipline_exception=bool(getattr(args, "discipline_exception", False)),
        exception_reason=str(getattr(args, "exception_reason", "") or ""),
    )
    persist_constraint_audit(
        build_constraint_audit_record("portfolio.plan-batch", {"strategy": batch.strategy, "status": batch.status}),
        log_path=getattr(args, "constraint_log", None),
        sqlite_path=getattr(args, "sqlite", None),
    )
    payload = batch.to_dict()
    persistence = {"persisted_count": 0, "skipped_existing_count": 0}
    if getattr(args, "record", False):
        persistence = append_unique_trade_plan_records(
            getattr(args, "log", Path("data/review/trade_plans.jsonl")),
            batch.plans,
            sqlite_path=getattr(args, "sqlite", None),
        )
        payload["persistence"] = persistence
    rendered = render_trade_plan_batch_markdown(batch) if getattr(args, "format", "json") == "markdown" else json.dumps(payload, ensure_ascii=False, indent=2)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(rendered)


def _trade_plan_from_args(args: argparse.Namespace) -> dict | None:
    path = getattr(args, "trade_plan", None)
    if not path:
        return None
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _battle_plan_from_args(args: argparse.Namespace) -> dict | None:
    path = getattr(args, "battle_plan", None)
    if not path:
        return None
    if not path.exists():
        raise FileNotFoundError(f"Battle plan not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Battle plan must be JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Battle plan JSON must be an object: {path}")
    return payload


def _execution_confirmation_from_args(args: argparse.Namespace) -> dict | None:
    path = getattr(args, "execution_confirm", None)
    if not path:
        return None
    if not path.exists():
        raise FileNotFoundError(f"Execution confirmation not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Execution confirmation must be JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Execution confirmation JSON must be an object: {path}")
    return payload


def _order_approval_from_args(args: argparse.Namespace) -> dict | None:
    path = getattr(args, "order_approval", None)
    if not path:
        return None
    if not path.exists():
        raise FileNotFoundError(f"Order approval not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Order approval must be JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Order approval JSON must be an object: {path}")
    return payload


def _assistant_payload_from_args(args: argparse.Namespace) -> dict:
    path = getattr(args, "assistant_json", None)
    if not path:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"Trading assistant JSON not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Trading assistant JSON must be JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Trading assistant JSON must be an object: {path}")
    return payload


def _battle_plan_payload_from_args(args: argparse.Namespace, frame: pd.DataFrame, pretrade_payload: dict | None = None) -> dict | None:
    battle_plan = _battle_plan_from_args(args)
    if battle_plan is not None:
        return battle_plan
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    strategy_health = _current_strategy_health(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=strategy_health,
    )
    temperature = calculate_market_temperature(frame, candidates).to_dict()
    allocation_plan = build_allocation_plan(
        candidates,
        temperature,
        cash=args.cash,
        max_positions=getattr(args, "top", 5),
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=strategy_health,
    )
    return build_final_battle_plan(
        {
            "market_temperature": temperature,
            "allocation_plan": allocation_plan.to_dict(),
            "holding_risk": {"status": "pass"},
            "holding_action_plan": {"status": "pass"},
            "exit_plan": {"status": "pass"},
            "strategy_health": [strategy_health] if strategy_health else [],
            "pretrade_checks": [pretrade_payload] if pretrade_payload else [],
        },
        limit=getattr(args, "top", 5),
    )


def _pretrade_payload_from_args(args: argparse.Namespace, frame: pd.DataFrame) -> dict:
    path = getattr(args, "pretrade_json", None)
    if path:
        if not path.exists():
            raise FileNotFoundError(f"Pretrade JSON not found: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Pretrade JSON must be an object: {path}")
        return payload
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    strategy_health = _current_strategy_health(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=strategy_health,
    )
    temperature = calculate_market_temperature(frame, candidates).to_dict()
    result = run_pretrade_check(
        candidates,
        temperature,
        symbol=args.symbol,
        entry_price=args.current_price,
        planned_pct=args.planned_pct,
        cash=args.cash,
        stop_price=getattr(args, "stop_price", None),
        target_price=getattr(args, "target_price", None),
        max_positions=getattr(args, "top", 5),
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=strategy_health,
    )
    return result.to_dict()


def _execution_confirmation_payload_from_args(
    args: argparse.Namespace,
    pretrade_payload: dict,
    frame: pd.DataFrame,
) -> dict:
    explicit = _execution_confirmation_from_args(args)
    if explicit is not None:
        return explicit
    battle_plan = _battle_plan_payload_from_args(args, frame, pretrade_payload)
    confirmation = build_execution_confirmation(
        pretrade_payload,
        battle_plan=battle_plan,
        symbol=args.symbol,
        current_price=args.current_price,
        planned_pct=args.planned_pct,
        cash=args.cash,
        reference_price=getattr(args, "reference_price", None),
        warn_scale=getattr(args, "warn_scale", 0.5),
        max_price_deviation_pct=getattr(args, "max_price_deviation_pct", 0.015),
        hard_chase_pct=getattr(args, "hard_chase_pct", 0.03),
        lot_size=getattr(args, "lot_size", 100),
    )
    return confirmation.to_dict()


def _trade_plan_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_trade_plan_records(args.sqlite)
    path = (
        getattr(args, "plan_log", None)
        or getattr(args, "trade_plan_log", None)
        or getattr(args, "log", None)
        or Path("data/review/trade_plans.jsonl")
    )
    return read_trade_plan_records(path)


def _execution_confirmation_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_execution_confirmation_records(args.sqlite)
    path = getattr(args, "confirm_log", None) or getattr(args, "log", None) or Path("data/review/execution_confirms.jsonl")
    return read_execution_confirmation_records(path)


def _lifecycle_snapshot_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_lifecycle_snapshot_records(args.sqlite)
    path = getattr(args, "lifecycle_log", None)
    if not path:
        return []
    return read_jsonl(path)


def _latest_review_lifecycle_snapshot_from_args(args: argparse.Namespace, *, limit: int = 20) -> dict:
    records = list(_lifecycle_snapshot_records_from_args(args))
    if records:
        records.sort(key=lambda item: str(item.get("snapshot_date", "") or item.get("created_at", "") or ""))
        return dict(records[-1])
    return _position_lifecycle_snapshot_from_args(args, limit=limit)


def _trade_plan_number(plan: dict | None, key: str, fallback: float | None) -> float | None:
    if plan and key in plan and plan.get(key) not in (None, ""):
        return float(plan.get(key))
    return fallback


def _trade_plan_text(plan: dict | None, key: str) -> str:
    if plan and key in plan:
        return str(plan.get(key, "") or "")
    return ""


def _trade_plan_tags(plan: dict | None) -> list[str]:
    if not plan:
        return []
    tags = ["trade-plan"]
    if str(plan.get("gate_status", "") or "") in {"warn", "block"}:
        tags.append(f"plan-{plan.get('gate_status')}")
    if plan.get("discipline_exception"):
        tags.append("discipline-exception")
    return tags


def _execution_confirm_tags(confirm: dict | None) -> list[str]:
    if not confirm:
        return []
    tags = ["execution-confirm"]
    status = str(confirm.get("status", "") or "")
    if status:
        tags.append(f"confirm-{status}")
    if int(confirm.get("suggested_quantity", 0) or 0) <= 0:
        tags.append("confirm-no-quantity")
    return tags


def _order_approval_tags(approval: dict | None) -> list[str]:
    if not approval:
        return []
    tags = ["order-approval"]
    status = str(approval.get("status", "") or "")
    if status:
        tags.append(f"approval-{status}")
    if int(approval.get("suggested_quantity", 0) or 0) <= 0:
        tags.append("approval-no-quantity")
    return tags


def _execution_confirm_text(confirm: dict | None, key: str) -> str:
    if confirm and key in confirm:
        return str(confirm.get(key, "") or "")
    return ""


def _execution_confirm_number(confirm: dict | None, key: str, fallback: float | None) -> float:
    if confirm and confirm.get(key) not in (None, ""):
        return float(confirm.get(key))
    return float(fallback or 0.0)


def _order_approval_text(approval: dict | None, key: str) -> str:
    if approval and key in approval:
        return str(approval.get(key, "") or "")
    return ""


def _order_approval_number(approval: dict | None, key: str, fallback: float | None) -> float:
    if approval and approval.get(key) not in (None, ""):
        return float(approval.get(key))
    return float(fallback or 0.0)


def _execution_confirm_optional_number(confirm: dict | None, key: str) -> float | None:
    if not confirm or confirm.get(key) in (None, ""):
        return None
    return float(confirm.get(key))


def _execution_confirm_nested_number(confirm: dict | None, parent: str, key: str, fallback: float | None) -> float | None:
    nested = dict((confirm or {}).get(parent) or {})
    if nested.get(key) not in (None, ""):
        return float(nested.get(key))
    return fallback


def _execution_confirm_name(confirm: dict | None) -> str:
    candidate = dict((confirm or {}).get("battle_candidate") or {})
    if candidate.get("name"):
        return str(candidate.get("name"))
    pretrade = dict((confirm or {}).get("pretrade_result") or {})
    snapshot = dict(pretrade.get("candidate_snapshot") or {})
    return str(snapshot.get("name", "") or "")


def _execution_confirm_reasons(confirm: dict | None) -> list[str]:
    reasons: list[str] = []
    for check in list((confirm or {}).get("checks", []) or []):
        if str(check.get("status", "") or "") in {"warn", "block"}:
            reasons.append(str(check.get("message", "") or ""))
    return [item for item in reasons if item]


def _trade_vs_confirm_price_gap(confirm: dict | None, trade_price: float) -> float | None:
    confirmation_price = _execution_confirm_optional_number(confirm, "current_price")
    if confirmation_price in (None, 0):
        return None
    return float(trade_price) / float(confirmation_price) - 1.0


def _filter_gate_records(records: list[dict], *, strategy: str = "", symbol: str = "") -> list[dict]:
    strategy = str(strategy or "").strip()
    symbol = str(symbol or "").strip()
    if symbol:
        symbol = symbol.zfill(6)
    filtered: list[dict] = []
    for record in records:
        if strategy and str(record.get("strategy", "") or "").strip() != strategy:
            continue
        if symbol and str(record.get("symbol", "") or "").strip().zfill(6) != symbol:
            continue
        filtered.append(record)
    return filtered


def run_review_promotions(args: argparse.Namespace) -> None:
    records = _sqlite_promotion_records(args.sqlite) if getattr(args, "sqlite", None) else read_promotion_records(args.log)
    summary = summarize_promotion_records(records, limit=args.limit)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def run_review_constraints(args: argparse.Namespace) -> None:
    records = _sqlite_constraint_records(args.sqlite) if getattr(args, "sqlite", None) else read_constraint_audit_records(args.log)
    summary = summarize_constraint_audit_records(records, limit=args.limit)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def run_review_discipline(args: argparse.Namespace) -> None:
    records = _discipline_records_from_args(args)
    summary = summarize_discipline_records(records, limit=args.limit)
    if getattr(args, "format", "json") == "markdown":
        print("\n".join(render_discipline_summary_lines(summary)))
        return
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def run_review_discipline_adherence(args: argparse.Namespace) -> None:
    summary = _discipline_adherence_summary_from_args(
        args,
        limit=getattr(args, "limit", 20),
        lookahead_days=getattr(args, "lookahead_days", 1),
    )
    if getattr(args, "format", "json") == "markdown":
        text = render_discipline_adherence_markdown(summary)
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def _sqlite_selection_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_selections()
    records: list[dict] = []
    for row in frame.to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            if not payload.get("strategy") and payload.get("strategy_name"):
                payload["strategy"] = payload["strategy_name"]
            records.append(payload)
            continue
        records.append(
            {
                "date": row.get("selected_at", ""),
                "strategy": row.get("strategy", ""),
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "close": row.get("close"),
                "reason": row.get("reason", ""),
                "entry_gate": row.get("entry_gate", ""),
                "dragon_state": row.get("dragon_state", ""),
                "dragon_tags": row.get("dragon_tags", ""),
                "dragon_score": row.get("dragon_score", 0),
                "seal_quality_score": row.get("seal_quality_score", 0),
            }
        )
    return records


def _sqlite_promotion_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_strategy_promotions()
    records: list[dict] = []
    for row in frame.sort_values(["created_at", "id"]).to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "created_at": row.get("created_at", ""),
                "summary": row.get("summary_path", ""),
                "output": row.get("output_path", ""),
                "strategy_name": row.get("strategy_name", ""),
                "strategy": row.get("strategy_name", ""),
                "ok": bool(row.get("ok")),
                "backtest_requested": bool(row.get("backtest_requested")),
                "buy_price_field": row.get("buy_price_field", ""),
                "cash": row.get("cash", 0),
                "validation": _loads_json_object(row.get("validation_json")),
                "backtest": _loads_json_object(row.get("backtest_json")),
            }
        )
    return records


def _sqlite_constraint_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_strategy_constraints()
    records: list[dict] = []
    for row in frame.sort_values(["created_at", "id"]).to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "created_at": row.get("created_at", ""),
                "source": row.get("source", ""),
                "strategy": row.get("strategy", ""),
                "symbol": row.get("symbol", ""),
                "alert_level": row.get("alert_level", ""),
                "action": row.get("action", ""),
                "alerts": _loads_json_array(row.get("alerts_json")),
                "note": row.get("note", ""),
            }
        )
    return records


def _sqlite_discipline_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_discipline_records()
    records: list[dict] = []
    for row in frame.sort_values(["record_date", "id"]).to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "created_at": row.get("created_at", ""),
                "date": row.get("record_date", ""),
                "source": row.get("source", ""),
                "status": row.get("status", ""),
                "advice": _loads_json_array(row.get("advice_json")),
                "gate_violation_count": row.get("gate_violation_count", 0),
                "missing_gate_count": row.get("missing_gate_count", 0),
                "avg_execution_deviation_pct": row.get("avg_execution_deviation_pct", 0),
                "holding_status": row.get("holding_status", ""),
                "target_exposure_pct": row.get("target_exposure_pct", 0),
                "allocated_pct": row.get("allocated_pct", 0),
            }
        )
    return records


def _sqlite_trade_plan_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_trade_plans()
    records: list[dict] = []
    for row in frame.sort_values(["trade_date", "id"]).to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "created_at": row.get("created_at", ""),
                "trade_date": row.get("trade_date", ""),
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "strategy": row.get("strategy", ""),
                "market_regime": row.get("market_regime", ""),
                "stance": row.get("stance", ""),
                "status": row.get("status", ""),
                "gate_status": row.get("gate_status", ""),
                "gate_reason": row.get("gate_reason", ""),
                "planned_pct": row.get("planned_pct", 0),
                "planned_value": row.get("planned_value", 0),
                "allowed_pct": row.get("allowed_pct", 0),
                "allowed_value": row.get("allowed_value", 0),
                "entry_price": row.get("entry_price", 0),
                "stop_price": row.get("stop_price"),
                "target_price": row.get("target_price"),
                "discipline_exception": bool(row.get("discipline_exception", 0)),
                "exception_reason": row.get("exception_reason", ""),
            }
        )
    return records


def _sqlite_position_action_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_position_action_plans()
    records: list[dict] = []
    for row in frame.sort_values(["action_date", "id"]).to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "created_at": row.get("created_at", ""),
                "action_date": row.get("action_date", ""),
                "status": row.get("status", ""),
                "total_actions": row.get("total_actions", 0),
                "exit_count": row.get("exit_count", 0),
                "reduce_count": row.get("reduce_count", 0),
                "watch_count": row.get("watch_count", 0),
                "hold_count": row.get("hold_count", 0),
                "action_items": _loads_json_array(row.get("action_items_json")),
                "actions": [],
            }
        )
    return records


def _sqlite_exit_plan_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_exit_plans()
    records: list[dict] = []
    for row in frame.sort_values(["plan_date", "id"]).to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "created_at": row.get("created_at", ""),
                "plan_date": row.get("plan_date", ""),
                "status": row.get("status", ""),
                "total_positions": row.get("total_positions", 0),
                "sell_all_count": row.get("sell_all_count", 0),
                "take_profit_count": row.get("take_profit_count", 0),
                "reduce_count": row.get("reduce_count", 0),
                "time_stop_count": row.get("time_stop_count", 0),
                "invalidated_count": row.get("invalidated_count", 0),
                "watch_count": row.get("watch_count", 0),
                "hold_count": row.get("hold_count", 0),
                "total_sell_quantity": row.get("total_sell_quantity", 0),
                "expected_cash_release": row.get("expected_cash_release", 0),
                "action_items": _loads_json_array(row.get("action_items_json")),
                "items": [],
            }
        )
    return records


def _sqlite_lifecycle_snapshot_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_lifecycle_snapshots()
    records: list[dict] = []
    for row in frame.sort_values(["snapshot_date", "id"]).to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "created_at": row.get("created_at", ""),
                "snapshot_date": row.get("snapshot_date", ""),
                "status": row.get("status", ""),
                "trade_plan": {"records": row.get("trade_plan_records", 0)},
                "lots": {
                    "open_lots": row.get("open_lots", 0),
                    "stale_open_lots": row.get("stale_open_lots", 0),
                },
                "holding_actions": {
                    "exit_count": row.get("action_exit_count", 0),
                    "reduce_count": row.get("action_reduce_count", 0),
                },
                "exit_plan": {
                    "sell_all_count": row.get("exit_sell_all_count", 0),
                    "take_profit_count": row.get("exit_take_profit_count", 0),
                },
                "execution": {
                    "trade_plan_match_rate": row.get("trade_plan_match_rate", 0),
                    "action_execution_rate": row.get("action_execution_rate", 0),
                    "exit_execution_rate": row.get("exit_execution_rate", 0),
                    "lot_exit_execution_rate": row.get("lot_exit_execution_rate", 0),
                },
            }
        )
    return records


def _sqlite_trading_day_state_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_trading_day_states()
    records: list[dict] = []
    for row in frame.sort_values(["state_date", "id"]).to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "created_at": row.get("created_at", ""),
                "date": row.get("state_date", ""),
                "source": row.get("source", ""),
                "status": row.get("status", ""),
                "phase_count": row.get("phase_count", 0),
                "pass_count": row.get("pass_count", 0),
                "warn_count": row.get("warn_count", 0),
                "block_count": row.get("block_count", 0),
                "action_item_count": row.get("action_item_count", 0),
                "phases": [],
                "action_items": [],
            }
        )
    return records


def _sqlite_order_approval_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_order_approvals()
    records: list[dict] = []
    if frame.empty:
        return records
    for row in frame.sort_values(["created_at", "id"]).to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "created_at": row.get("created_at", ""),
                "symbol": row.get("symbol", ""),
                "status": row.get("status", ""),
                "decision": row.get("decision", ""),
                "confirmed_pct": row.get("confirmed_pct", 0),
                "confirmed_value": row.get("confirmed_value", 0),
                "suggested_quantity": row.get("suggested_quantity", 0),
                "evidence": _loads_json_object(row.get("evidence_json")),
                "reasons": _loads_json_array(row.get("reasons_json")),
                "action_items": _loads_json_array(row.get("action_items_json")),
            }
        )
    return records


def _sqlite_execution_confirmation_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_execution_confirmations()
    records: list[dict] = []
    if frame.empty:
        return records
    for row in frame.sort_values(["created_at", "id"]).to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "created_at": row.get("created_at", ""),
                "symbol": row.get("symbol", ""),
                "status": row.get("status", ""),
                "decision": row.get("decision", ""),
                "current_price": row.get("current_price", 0),
                "reference_price": row.get("reference_price"),
                "price_deviation_pct": row.get("price_deviation_pct"),
                "requested_pct": row.get("requested_pct", 0),
                "confirmed_pct": row.get("confirmed_pct", 0),
                "requested_value": row.get("requested_value", 0),
                "confirmed_value": row.get("confirmed_value", 0),
                "suggested_quantity": row.get("suggested_quantity", 0),
                "lot_size": row.get("lot_size", 100),
                "final_gate_status": row.get("final_gate_status", ""),
                "pretrade_status": row.get("pretrade_status", ""),
                "checks": _loads_json_array(row.get("checks_json")),
                "action_items": _loads_json_array(row.get("action_items_json")),
            }
        )
    return records


def _existing_fingerprints_for_review_source(store: SQLiteStore, name: str) -> set[str]:
    readers = {
        "selections": store.read_selections,
        "trades": store.read_trades,
        "promotions": store.read_strategy_promotions,
        "constraints": store.read_strategy_constraints,
        "discipline": store.read_discipline_records,
        "trade_plans": store.read_trade_plans,
        "action_plans": store.read_position_action_plans,
        "exit_plans": store.read_exit_plans,
        "lifecycle_snapshots": store.read_lifecycle_snapshots,
        "trading_day_states": store.read_trading_day_states,
        "order_approvals": store.read_order_approvals,
        "execution_confirmations": store.read_execution_confirmations,
    }
    reader = readers.get(name)
    if reader is None:
        return set()
    frame = reader()
    if frame.empty or "payload_json" not in frame.columns:
        return set()
    result: set[str] = set()
    for value in frame["payload_json"].tolist():
        payload = _loads_json_object(value)
        if payload:
            result.add(_record_fingerprint(payload))
    return result


def _dedupe_review_records(records: list[dict], existing: set[str]) -> list[dict]:
    result: list[dict] = []
    seen = set(existing)
    for record in records:
        fingerprint = _record_fingerprint(record)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        result.append(record)
    return result


def _record_fingerprint(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)


def _trade_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_trade_records(args.sqlite)
    path = getattr(args, "trade_log", None) or getattr(args, "journal", None) or Path("data/review/trades.jsonl")
    return TradeJournal(path).list()


def _discipline_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_discipline_records(args.sqlite)
    path = getattr(args, "discipline_log", None) or getattr(args, "log", None) or Path("data/review/discipline.jsonl")
    return read_discipline_records(path)


def _trading_day_state_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_trading_day_state_records(args.sqlite)
    path = getattr(args, "state_log", None) or Path("data/review/trading_day_states.jsonl")
    return read_trading_day_state_records(path)


def _order_approval_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_order_approval_records(args.sqlite)
    path = getattr(args, "approval_log", None) or getattr(args, "log", None) or Path("data/review/order_approvals.jsonl")
    return read_order_approval_records(path)


def _persist_trading_day_state_from_args(args: argparse.Namespace, source: str, timeline: dict) -> dict:
    state = build_trading_day_state(
        timeline,
        trading_date=str(getattr(args, "as_of", "") or "")[:10],
        source=source,
    )
    if getattr(args, "record_state", False):
        append_trading_day_state_record(
            getattr(args, "state_log", Path("data/review/trading_day_states.jsonl")),
            state,
            sqlite_path=getattr(args, "sqlite", None),
        )
    return state


def _trading_day_watchdog_from_args(args: argparse.Namespace, current_state: dict | None = None) -> dict:
    records = list(_trading_day_state_records_from_args(args))
    if current_state:
        current_fingerprint = _record_fingerprint(current_state)
        if all(_record_fingerprint(record) != current_fingerprint for record in records):
            records.append(current_state)
    return build_trading_day_watchdog(
        records,
        as_of=getattr(args, "as_of", None),
        repeat_threshold=getattr(args, "repeat_threshold", 2),
        stale_days=getattr(args, "stale_days", 1),
        limit=getattr(args, "limit", getattr(args, "top", 20)),
    )


def _persist_discipline_from_args(
    args: argparse.Namespace,
    source: str,
    *,
    gate_review: dict | None = None,
    trade_stats: dict | None = None,
    holding_risk: dict | None = None,
    allocation_plan: dict | None = None,
) -> None:
    if not getattr(args, "record_discipline", False):
        return
    record = build_discipline_record(
        source=source,
        gate_review=gate_review,
        trade_stats=trade_stats,
        holding_risk=holding_risk,
        allocation_plan=allocation_plan,
    )
    persist_discipline_record(
        record,
        log_path=getattr(args, "discipline_log", None),
        sqlite_path=getattr(args, "sqlite", None),
    )


def _promotion_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_promotion_records(args.sqlite)
    path = getattr(args, "promotion_log", None) or getattr(args, "log", None) or Path("data/review/promotions.jsonl")
    return read_promotion_records(path)


def _trade_plan_pressure_from_args(args: argparse.Namespace) -> dict[str, float | int]:
    if getattr(args, "sqlite", None):
        records = _sqlite_trade_plan_records(args.sqlite)
    else:
        path = getattr(args, "trade_plan_log", None)
        if not path:
            return {}
        records = read_trade_plan_records(path)
    if not records:
        return {}
    pressure = summarize_trade_plan_audit(records, _trade_records_from_args(args), limit=20)
    return {
        "total_plans": int(pressure.get("total_plans", 0) or 0),
        "match_rate": float(pressure.get("match_rate", 0) or 0),
        "unmatched_plans": int(pressure.get("unmatched_plans", 0) or 0),
        "orphan_trades": int(pressure.get("orphan_trades", 0) or 0),
        "avg_price_deviation_pct": float(pressure.get("avg_price_deviation_pct", 0) or 0),
    }


def _strategy_health_from_args(args: argparse.Namespace) -> list[dict]:
    selections = _selection_records_from_args(args)
    trades = _trade_records_from_args(args)
    promotions = _promotion_records_from_args(args)
    if not (selections or trades or promotions):
        return []
    audit_map = _trade_plan_audit_by_strategy_from_args(args)
    trade_plan_records = _trade_plan_records_from_args(args)
    action_plan_records = _position_action_records_from_args(args)
    exit_plan_records = _exit_plan_records_from_args(args)
    lifecycle_records = _lifecycle_snapshot_records_from_args(args)
    lifecycle_snapshot = _position_lifecycle_snapshot_from_args(args, limit=20)
    has_review_memory = bool(lifecycle_records or trade_plan_records or action_plan_records or exit_plan_records)
    lifecycle_pressure = {}
    if has_review_memory:
        lifecycle_window = _merge_lifecycle_snapshots(lifecycle_records, lifecycle_snapshot)
        doctor_report = _review_doctor_from_args(
            args,
            trade_plans=trade_plan_records,
            action_plans=action_plan_records,
            exit_plans=exit_plan_records,
            lifecycle_snapshots=lifecycle_window,
        )
        lifecycle_pressure = build_review_memory_pressure(
            lifecycle_snapshots=lifecycle_window,
            doctor_report=doctor_report,
            limit=5,
        )
    if not lifecycle_pressure and lifecycle_snapshot:
        lifecycle_pressure = build_lifecycle_pressure(lifecycle_snapshot)
    strategy_health = summarize_strategy_health(
        selections,
        trades,
        promotions,
        trade_plan_audits=audit_map,
        lifecycle_pressure=lifecycle_pressure,
    )
    constraint_records = _constraint_records_from_args(args)
    return [
        apply_constraint_policy_to_health(
            item.to_dict(),
            constraint_records,
            **_constraint_policy_kwargs_from_args(args, item.strategy),
        )
        for item in strategy_health
    ]


def _current_strategy_health(args: argparse.Namespace) -> dict:
    strategy = getattr(args, "_resolved_strategy", None)
    strategy_name = str(getattr(strategy, "name", "") or getattr(args, "strategy", "") or "").strip()
    if not strategy_name:
        return {}
    base = {"strategy": strategy_name, "alert_level": "pass", "action": "keep", "alerts": []}
    for item in _strategy_health_from_args(args):
        if str(item.get("strategy", "")).strip() == strategy_name:
            base = item
            break
    return apply_constraint_policy_to_health(
        base,
        _constraint_records_from_args(args),
        **_constraint_policy_kwargs_from_args(args, strategy_name),
    )


def _review_doctor_from_args(
    args: argparse.Namespace,
    *,
    trade_plans: list[dict] | None = None,
    action_plans: list[dict] | None = None,
    exit_plans: list[dict] | None = None,
    lifecycle_snapshots: list[dict] | None = None,
    trading_day_states: list[dict] | None = None,
) -> dict:
    return build_review_doctor_report(
        selections=_selection_records_from_args(args),
        trades=_trade_records_from_args(args),
        trade_plans=list(trade_plans if trade_plans is not None else _trade_plan_records_from_args(args)),
        execution_confirmations=_execution_confirmation_records_from_args(args),
        action_plans=list(action_plans if action_plans is not None else _position_action_records_from_args(args)),
        exit_plans=list(exit_plans if exit_plans is not None else _exit_plan_records_from_args(args)),
        lifecycle_snapshots=list(lifecycle_snapshots if lifecycle_snapshots is not None else _lifecycle_snapshot_records_from_args(args)),
        trading_day_states=list(trading_day_states if trading_day_states is not None else _trading_day_state_records_from_args(args)),
    )


def _merge_lifecycle_snapshots(records: list[dict], current_snapshot: dict | None) -> list[dict]:
    merged = list(records or [])
    if not current_snapshot:
        return merged
    current_date = str(current_snapshot.get("snapshot_date", "") or "")
    current_status = str(current_snapshot.get("status", "") or "")
    if merged and not current_date:
        return merged
    for item in merged:
        if (
            str(item.get("snapshot_date", "") or "") == current_date
            and str(item.get("status", "") or "") == current_status
        ):
            return merged
    merged.append(current_snapshot)
    merged.sort(key=lambda item: str(item.get("snapshot_date", "") or item.get("created_at", "") or ""))
    return merged


def _pretrade_preview_from_report_inputs(
    candidates: list[dict] | pd.DataFrame,
    allocation_plan: dict | None,
    market_temperature: dict | None,
    settings: SystemSettings,
    strategy_health: dict | None,
    *,
    cash: float,
    max_positions: int,
) -> list[dict]:
    if allocation_plan is None:
        return []
    if isinstance(candidates, pd.DataFrame):
        frame = candidates.copy()
        records = frame.to_dict(orient="records")
    else:
        records = list(candidates)
    if not records:
        return []

    candidate_map = {
        str(item.get("symbol", "")).strip().zfill(6): item
        for item in records
        if str(item.get("symbol", "")).strip()
    }
    previews: list[dict] = []
    for item in (allocation_plan.get("items", []) or [])[: max(max_positions, 1)]:
        symbol = str(item.get("symbol", "")).strip().zfill(6)
        candidate = candidate_map.get(symbol)
        if not candidate:
            continue
        entry_price = _float_or_none(candidate.get("close"))
        if entry_price is None:
            continue
        stop_price = _float_or_none(item.get("stop_price"))
        if stop_price is None:
            stop_price = _float_or_none(candidate.get("atr_stop_price"))
        target_price = _preview_target_price(entry_price, stop_price)
        result = run_pretrade_check(
            pd.DataFrame(records),
            market_temperature or {},
            symbol=symbol,
            entry_price=entry_price,
            planned_pct=float(item.get("target_pct", 0) or 0),
            cash=cash,
            stop_price=stop_price,
            target_price=target_price,
            max_positions=max_positions,
            regime_exposure=settings.risk.regime_exposure,
            cap_by_risk=settings.risk.cap_by_risk,
            strategy_health=strategy_health,
        )
        previews.append(result.to_dict())
    return previews


def _preview_target_price(entry_price: float, stop_price: float | None) -> float:
    if stop_price is not None and stop_price < entry_price:
        return round(entry_price + (entry_price - stop_price) * 2.0, 2)
    return round(entry_price * 1.08, 2)


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)


def _constraint_summary_from_args(args: argparse.Namespace, limit: int = 10) -> dict:
    return summarize_constraint_audit_records(_constraint_records_from_args(args), limit=limit)


def _discipline_summary_from_args(args: argparse.Namespace, limit: int = 10) -> dict:
    return summarize_discipline_records(_discipline_records_from_args(args), limit=limit)


def _discipline_adherence_summary_from_args(
    args: argparse.Namespace,
    limit: int = 10,
    lookahead_days: int = 1,
) -> dict:
    return evaluate_discipline_adherence(
        _discipline_records_from_args(args),
        _trade_records_from_args(args),
        lookahead_days=lookahead_days,
        limit=limit,
    )


def _constraint_records_from_args(args: argparse.Namespace) -> list[dict]:
    sqlite_path = getattr(args, "sqlite", None)
    if sqlite_path:
        records = _sqlite_constraint_records(sqlite_path)
    else:
        path = getattr(args, "constraint_log", None) or Path("data/review/strategy_constraints.jsonl")
        records = read_constraint_audit_records(path)
    auto_constraints = _auto_approval_cooldown_constraints_from_args(args)
    return _merge_constraint_records(records, auto_constraints)


def _approval_cooldown_payload_from_args(args: argparse.Namespace) -> dict:
    cached = getattr(args, "_auto_approval_cooldown_payload", None)
    if isinstance(cached, dict):
        return cached
    if getattr(args, "disable_approval_cooldown", False):
        payload = summarize_approval_cooldown([])
        payload["approval_audit"] = {}
        args._auto_approval_cooldown_payload = payload
        return payload
    audit_summary = summarize_approval_execution(
        _order_approval_records_from_args(args),
        _trade_records_from_args(args),
        lookahead_days=getattr(args, "approval_lookahead_days", getattr(args, "lookahead_days", 1)),
        value_tolerance_pct=getattr(args, "approval_value_tolerance_pct", getattr(args, "value_tolerance_pct", 0.02)),
        limit=getattr(args, "limit", 20) or 20,
    )
    constraints = build_approval_cooldown_constraints(
        audit_summary,
        block_threshold=getattr(args, "approval_block_threshold", getattr(args, "block_threshold", 1)),
        warn_threshold=getattr(args, "approval_warn_threshold", getattr(args, "warn_threshold", 2)),
        fallback_threshold=getattr(args, "approval_fallback_threshold", getattr(args, "fallback_threshold", 2)),
        warn_exposure_multiplier=getattr(args, "approval_warn_exposure_multiplier", getattr(args, "warn_exposure_multiplier", 0.5)),
    )
    payload = summarize_approval_cooldown(constraints)
    payload["approval_audit"] = audit_summary
    args._auto_approval_cooldown_payload = payload
    return payload


def _auto_approval_cooldown_constraints_from_args(args: argparse.Namespace) -> list[dict]:
    return list(_approval_cooldown_payload_from_args(args).get("constraints") or [])


def _record_auto_approval_cooldown_from_args(args: argparse.Namespace) -> dict:
    payload = _approval_cooldown_payload_from_args(args)
    constraints = list(payload.get("constraints") or [])
    existing = _constraint_records_without_auto(args)
    existing_keys = {_constraint_record_identity(record) for record in existing}
    imported = 0
    skipped = 0
    if getattr(args, "record_approval_cooldown", False):
        for record in constraints:
            key = _constraint_record_identity(record)
            if key in existing_keys:
                skipped += 1
                continue
            persist_constraint_audit(
                record,
                log_path=getattr(args, "constraint_log", None),
                sqlite_path=getattr(args, "sqlite", None),
            )
            existing_keys.add(key)
            imported += 1
    result = dict(payload)
    result["persisted_count"] = imported
    result["skipped_existing_count"] = skipped
    result["record_requested"] = bool(getattr(args, "record_approval_cooldown", False))
    return result


def _persist_attribution_policy(args: argparse.Namespace, policy: dict) -> dict:
    constraints = list(policy.get("constraints") or [])
    existing = _constraint_records_without_auto(args)
    existing_keys = {_constraint_record_identity(record) for record in existing}
    persisted = 0
    skipped = 0
    for record in constraints:
        key = _constraint_record_identity(record)
        if key in existing_keys:
            skipped += 1
            continue
        persist_constraint_audit(
            record,
            log_path=getattr(args, "constraint_log", None),
            sqlite_path=getattr(args, "sqlite", None),
        )
        existing_keys.add(key)
        persisted += 1
    discipline_record = dict(policy.get("discipline_record") or {})
    if discipline_record:
        persist_discipline_record(
            discipline_record,
            log_path=getattr(args, "discipline_log", None),
            sqlite_path=getattr(args, "sqlite", None),
        )
    policy["persisted_count"] = persisted
    policy["skipped_existing_count"] = skipped
    policy["discipline_persisted"] = bool(discipline_record)
    return {
        "persisted_count": persisted,
        "skipped_existing_count": skipped,
        "discipline_persisted": bool(discipline_record),
    }


def _constraint_records_without_auto(args: argparse.Namespace) -> list[dict]:
    sqlite_path = getattr(args, "sqlite", None)
    if sqlite_path:
        return _sqlite_constraint_records(sqlite_path)
    path = getattr(args, "constraint_log", None) or Path("data/review/strategy_constraints.jsonl")
    return read_constraint_audit_records(path)


def _merge_constraint_records(records: list[dict], auto_constraints: list[dict]) -> list[dict]:
    merged = list(records or [])
    seen = {_constraint_record_identity(record) for record in merged}
    for record in auto_constraints:
        key = _constraint_record_identity(record)
        if key in seen:
            continue
        seen.add(key)
        merged.append(record)
    return merged


def _constraint_record_identity(record: dict) -> str:
    return json.dumps(
        {
            "date": str(record.get("created_at", "") or "")[:10],
            "source": record.get("source", ""),
            "strategy": record.get("strategy", ""),
            "symbol": record.get("symbol", ""),
            "alert_level": record.get("alert_level", ""),
            "action": record.get("action", ""),
            "alerts": sorted(str(item) for item in list(record.get("alerts") or [])),
            "note": record.get("note", ""),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _selection_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_selection_records(args.sqlite)
    tracker = getattr(args, "tracker", None) or Path("data/review/selections.jsonl")
    return SelectionTracker(tracker).history()


def _trade_plan_audit_by_strategy_from_args(args: argparse.Namespace) -> dict[str, dict]:
    plan_records = _trade_plan_records_from_args(args)
    trade_records = _trade_records_from_args(args)
    if not plan_records or not trade_records:
        return {}
    return summarize_trade_plan_audit(plan_records, trade_records, limit=20).get("by_strategy", {}) or {}


def _action_execution_summary_from_args(
    args: argparse.Namespace,
    *,
    trade_records: list[dict] | None = None,
    limit: int = 10,
) -> dict | None:
    records = _position_action_records_from_args(args)
    if not records:
        return None
    trades = trade_records if trade_records is not None else _trade_records_from_args(args)
    return summarize_action_execution(records, trades, lookahead_days=getattr(args, "lookahead_days", 3), limit=limit)


def _latest_exit_plan_from_args(args: argparse.Namespace) -> dict | None:
    records = _exit_plan_records_from_args(args)
    if not records:
        return None
    return records[-1]


def _exit_execution_summary_from_args(
    args: argparse.Namespace,
    *,
    trade_records: list[dict] | None = None,
    limit: int = 10,
) -> dict | None:
    records = _exit_plan_records_from_args(args)
    if not records:
        return None
    trades = trade_records if trade_records is not None else _trade_records_from_args(args)
    return summarize_exit_execution(records, trades, lookahead_days=getattr(args, "lookahead_days", 3), limit=limit)


def _lot_exit_execution_summary_from_args(
    args: argparse.Namespace,
    *,
    trade_records: list[dict] | None = None,
    limit: int = 10,
) -> dict | None:
    records = _exit_plan_records_from_args(args)
    if not records:
        return None
    trades = trade_records if trade_records is not None else _trade_records_from_args(args)
    return summarize_lot_exit_execution(records, trades, lookahead_days=getattr(args, "lookahead_days", 3), limit=limit)


def _position_lifecycle_snapshot_from_args(args: argparse.Namespace, *, limit: int = 20) -> dict:
    prices = parse_price_overrides(getattr(args, "price", []) or [])
    stops = parse_price_overrides(getattr(args, "stop", []) or [])
    trade_records = _trade_records_from_args(args)
    lot_book = build_lot_book(trade_records, prices=prices, as_of=getattr(args, "as_of", None)).to_dict()
    position_book = build_position_book(trade_records, cash=getattr(args, "cash", 100000), prices=prices)
    lifecycle_rule_plan = build_lifecycle_rule_plan(
        position_book,
        stops=stops,
        discipline_summary=summarize_trade_journal(trade_records),
        max_probe_pct=getattr(args, "max_probe_pct", 0.05),
        max_position_pct=getattr(args, "max_position_pct", 0.2),
        add_step_pct=getattr(args, "add_step_pct", 0.05),
        add_profit_trigger_pct=getattr(args, "add_profit_trigger_pct", 0.03),
        reduce_loss_warning_pct=getattr(args, "reduce_loss_warning_pct", 0.03),
    ).to_dict()
    trade_plan_summary = build_trade_plan_summary(_trade_plan_records_from_args(args), limit=limit)
    action_execution_summary = _action_execution_summary_from_args(args, trade_records=trade_records, limit=limit)
    exit_execution_summary = _exit_execution_summary_from_args(args, trade_records=trade_records, limit=limit)
    lot_exit_execution_summary = _lot_exit_execution_summary_from_args(args, trade_records=trade_records, limit=limit)
    holding_action_plan = None
    action_records = _position_action_records_from_args(args)
    if action_records:
        holding_action_plan = action_records[-1]
    exit_plan = _latest_exit_plan_from_args(args)
    trade_plan_audit = summarize_trade_plan_audit(_trade_plan_records_from_args(args), trade_records, limit=limit)
    return build_position_lifecycle_snapshot(
        trade_plan_summary=trade_plan_summary,
        lot_book=lot_book,
        holding_action_plan=holding_action_plan,
        exit_plan=exit_plan,
        lifecycle_rule_plan=lifecycle_rule_plan,
        trade_plan_audit=trade_plan_audit,
        action_execution_summary=action_execution_summary,
        exit_execution_summary=exit_execution_summary,
        lot_exit_execution_summary=lot_exit_execution_summary,
    )


def _position_action_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_position_action_records(args.sqlite)
    action_log = getattr(args, "action_log", None)
    if not action_log:
        return []
    return read_position_action_plan_records(action_log)


def _exit_plan_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_exit_plan_records(args.sqlite)
    exit_log = getattr(args, "exit_log", None)
    if not exit_log:
        return []
    return read_exit_plan_records(exit_log)


def _constraint_policy_kwargs_from_args(args: argparse.Namespace, strategy: str = "") -> dict:
    policy = settings_from_args(args).risk.constraint_policy
    kwargs = dict(policy.kwargs_for(strategy or str(getattr(args, "strategy", "") or "")))
    as_of = _policy_as_of_from_args(args)
    if as_of is not None:
        kwargs["as_of"] = as_of
    return kwargs


def _policy_as_of_from_args(args: argparse.Namespace) -> date | None:
    value = str(getattr(args, "as_of", "") or getattr(args, "date", "") or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError:
        return None


def _sqlite_trade_records(sqlite_path: Path) -> list[dict]:
    frame = SQLiteStore(sqlite_path).read_trades()
    records: list[dict] = []
    if frame.empty:
        return records
    frame = frame.sort_values(["trade_date", "id"])
    for row in frame.to_dict(orient="records"):
        payload = _loads_json_object(row.get("payload_json"))
        if payload:
            records.append(payload)
            continue
        records.append(
            {
                "date": row.get("trade_date", ""),
                "symbol": row.get("symbol", ""),
                "side": row.get("side", ""),
                "price": row.get("price", 0),
                "quantity": row.get("quantity", 0),
                "reason": row.get("reason", ""),
                "name": row.get("name", ""),
                "strategy": row.get("strategy", ""),
                "market_regime": row.get("market_regime", ""),
                "planned_pct": row.get("planned_pct", 0),
                "actual_pct": row.get("actual_pct", 0),
                "planned_price": row.get("planned_price"),
                "stop_price": row.get("stop_price"),
                "target_price": row.get("target_price"),
                "amount": row.get("amount", 0),
                "execution_deviation_pct": row.get("execution_deviation_pct"),
                "tags": _loads_json_array(row.get("tags_json")),
                "mistake_type": row.get("mistake_type", ""),
                "review": row.get("review", ""),
                "gate_status": row.get("gate_status", ""),
                "gate_message": row.get("gate_message", ""),
                "gate_reasons": _loads_json_array(row.get("gate_reasons_json")),
                "workflow_summary": row.get("workflow_summary", ""),
                "discipline_exception": bool(row.get("discipline_exception", 0)),
                "exception_reason": row.get("exception_reason", ""),
                "order_approval_path": row.get("order_approval_path", ""),
                "order_approval_created_at": row.get("order_approval_created_at", ""),
                "order_approval_status": row.get("order_approval_status", ""),
                "order_approval_decision": row.get("order_approval_decision", ""),
                "approved_pct": row.get("approved_pct", 0),
                "approved_value": row.get("approved_value", 0),
                "approved_quantity": row.get("approved_quantity", 0),
            }
        )
    return records


def _loads_json_object(value: object) -> dict:
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _loads_json_array(value: object) -> list:
    if not value:
        return []
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []

def run_market_temperature(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=_current_strategy_health(args),
        only_top_sectors=False,
    )
    temperature = calculate_market_temperature(frame, candidates)
    print(json.dumps(temperature.to_dict(), ensure_ascii=False, indent=2))

def run_market_sectors(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=_current_strategy_health(args),
        only_top_sectors=False,
        sector_top=args.top,
        top=0,
    )
    sectors = calculate_sector_strength(frame, candidates, sector_column=args.sector_column, top=args.top)
    print(json.dumps(sectors.to_dict(orient="records"), ensure_ascii=False, indent=2, default=str))

def run_portfolio_allocate(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    strategy_health = _current_strategy_health(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=strategy_health,
    )
    temperature = calculate_market_temperature(frame, candidates).to_dict()
    plan = build_allocation_plan(
        candidates,
        temperature,
        cash=args.cash,
        max_positions=args.top,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=strategy_health,
    )
    persist_constraint_audit(
        build_constraint_audit_record("portfolio.allocate", plan.strategy_constraint),
        log_path=getattr(args, "constraint_log", None),
        sqlite_path=getattr(args, "sqlite", None),
    )
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))

def run_portfolio_precheck(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    strategy_health = _current_strategy_health(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=strategy_health,
    )
    temperature = calculate_market_temperature(frame, candidates).to_dict()
    result = run_pretrade_check(
        candidates,
        temperature,
        symbol=args.symbol,
        entry_price=args.entry_price,
        planned_pct=args.planned_pct,
        cash=args.cash,
        stop_price=args.stop_price,
        target_price=args.target_price,
        max_positions=args.top,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=strategy_health,
    )
    persist_constraint_audit(
        build_constraint_audit_record("portfolio.precheck", result.strategy_constraint, symbol=args.symbol),
        log_path=getattr(args, "constraint_log", None),
        sqlite_path=getattr(args, "sqlite", None),
    )
    if getattr(args, "format", "json") == "markdown":
        print(render_precheck_markdown(result, temperature, settings_from_args(args)))
        return
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


def run_portfolio_confirm(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    strategy_health = _current_strategy_health(args)
    candidates = screened_candidates_from_args(
        args,
        frame,
        strategy=strategy,
        settings=settings,
        strategy_health=strategy_health,
    )
    temperature = calculate_market_temperature(frame, candidates).to_dict()
    allocation_plan = build_allocation_plan(
        candidates,
        temperature,
        cash=args.cash,
        max_positions=args.top,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=strategy_health,
    )
    pretrade_result = run_pretrade_check(
        candidates,
        temperature,
        symbol=args.symbol,
        entry_price=args.current_price,
        planned_pct=args.planned_pct,
        cash=args.cash,
        stop_price=args.stop_price,
        target_price=args.target_price,
        max_positions=args.top,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=strategy_health,
    )
    battle_plan = _battle_plan_from_args(args)
    if battle_plan is None:
        battle_plan = build_final_battle_plan(
            {
                "market_temperature": temperature,
                "allocation_plan": allocation_plan.to_dict(),
                "holding_risk": {"status": "pass"},
                "holding_action_plan": {"status": "pass"},
                "exit_plan": {"status": "pass"},
                "strategy_health": [strategy_health] if strategy_health else [],
                "pretrade_checks": [pretrade_result.to_dict()],
            },
            limit=args.top,
        )
    confirmation = build_execution_confirmation(
        pretrade_result,
        battle_plan=battle_plan,
        symbol=args.symbol,
        current_price=args.current_price,
        planned_pct=args.planned_pct,
        cash=args.cash,
        reference_price=getattr(args, "reference_price", None),
        warn_scale=args.warn_scale,
        max_price_deviation_pct=args.max_price_deviation_pct,
        hard_chase_pct=args.hard_chase_pct,
        lot_size=args.lot_size,
    )
    persist_constraint_audit(
        build_constraint_audit_record("portfolio.confirm", pretrade_result.strategy_constraint, symbol=args.symbol),
        log_path=getattr(args, "constraint_log", None),
        sqlite_path=getattr(args, "sqlite", None),
    )
    if getattr(args, "record", False):
        append_execution_confirmation_record(
            getattr(args, "log", Path("data/review/execution_confirms.jsonl")),
            confirmation,
            sqlite_path=getattr(args, "sqlite", None),
        )
    payload = confirmation.to_dict()
    rendered = (
        render_execution_confirmation_markdown(confirmation)
        if getattr(args, "format", "json") == "markdown"
        else json.dumps(payload, ensure_ascii=False, indent=2)
    )
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(rendered)


def run_portfolio_tradable(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    pretrade_payload = _pretrade_payload_from_args(args, frame)
    confirmation_payload = _execution_confirmation_payload_from_args(args, pretrade_payload, frame)
    battle_plan = _battle_plan_payload_from_args(args, frame, pretrade_payload)
    result = build_tradability_check(
        frame,
        symbol=args.symbol,
        current_price=args.current_price,
        planned_pct=args.planned_pct,
        cash=args.cash,
        pretrade_result=pretrade_payload,
        confirmation=confirmation_payload,
        battle_plan=battle_plan,
        as_of=getattr(args, "as_of", None),
        max_stale_days=args.max_stale_days,
        limit_pct=args.limit_pct,
        limit_buffer_pct=args.limit_buffer_pct,
        lot_size=args.lot_size,
    )
    payload = result.to_dict()
    rendered = render_tradability_markdown(result) if getattr(args, "format", "json") == "markdown" else json.dumps(payload, ensure_ascii=False, indent=2)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(rendered)


def run_portfolio_approve(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    assistant_payload = _assistant_payload_from_args(args)
    pretrade_payload = _pretrade_payload_from_args(args, frame)
    confirmation_payload = _execution_confirmation_payload_from_args(args, pretrade_payload, frame)
    battle_plan = _battle_plan_payload_from_args(args, frame, pretrade_payload)
    tradability_result = build_tradability_check(
        frame,
        symbol=args.symbol,
        current_price=args.current_price,
        planned_pct=args.planned_pct,
        cash=args.cash,
        pretrade_result=pretrade_payload,
        confirmation=confirmation_payload,
        battle_plan=battle_plan,
        as_of=getattr(args, "as_of", None),
        max_stale_days=args.max_stale_days,
        limit_pct=args.limit_pct,
        limit_buffer_pct=args.limit_buffer_pct,
        lot_size=args.lot_size,
    )
    approval = build_order_approval(
        symbol=args.symbol,
        assistant=assistant_payload,
        battle_plan=battle_plan,
        pretrade=pretrade_payload,
        confirmation=confirmation_payload,
        tradability=tradability_result.to_dict(),
    )
    if getattr(args, "record", False):
        append_order_approval_record(
            getattr(args, "log", Path("data/review/order_approvals.jsonl")),
            approval,
            sqlite_path=getattr(args, "sqlite", None),
        )
    rendered = (
        render_order_approval_markdown(approval)
        if getattr(args, "format", "json") == "markdown"
        else json.dumps(approval, ensure_ascii=False, indent=2, default=str)
    )
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(rendered)


def run_portfolio_positions(args: argparse.Namespace) -> None:
    prices = parse_price_overrides(args.price)
    records = _trade_records_from_args(args)
    book = build_position_book(records, cash=args.cash, prices=prices)
    print(json.dumps(book.to_dict(), ensure_ascii=False, indent=2))


def run_portfolio_lots(args: argparse.Namespace) -> None:
    prices = parse_price_overrides(getattr(args, "price", []) or [])
    records = _trade_records_from_args(args)
    book = build_lot_book(records, prices=prices, as_of=getattr(args, "as_of", None))
    if getattr(args, "record", False):
        append_lot_book_record(getattr(args, "log", Path("data/review/lot_books.jsonl")), book)
    text = render_lot_book_markdown(book) if getattr(args, "format", "json") == "markdown" else json.dumps(book.to_dict(), ensure_ascii=False, indent=2)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_portfolio_lifecycle(args: argparse.Namespace) -> None:
    snapshot = _position_lifecycle_snapshot_from_args(args, limit=getattr(args, "limit", 20))
    if getattr(args, "record", False) and getattr(args, "sqlite", None):
        payload = dict(snapshot)
        payload["created_at"] = datetime.now(timezone.utc).isoformat()
        payload["snapshot_date"] = str(getattr(args, "as_of", "") or date.today().isoformat())
        store = SQLiteStore(args.sqlite)
        store.init()
        store.insert_lifecycle_snapshot(payload, snapshot_date=payload["snapshot_date"])
    text = render_position_lifecycle_markdown(snapshot) if getattr(args, "format", "json") == "markdown" else json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_portfolio_risk(args: argparse.Namespace) -> None:
    prices = parse_price_overrides(args.price)
    stops = parse_price_overrides(args.stop)
    records = _trade_records_from_args(args)
    book = build_position_book(records, cash=args.cash, prices=prices)
    report = check_holding_risk(
        book,
        stops=stops,
        max_exposure_pct=args.max_exposure_pct,
        max_position_pct=args.max_position_pct,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))


def run_portfolio_actions(args: argparse.Namespace) -> None:
    prices = parse_price_overrides(args.price)
    stops = parse_price_overrides(args.stop)
    records = _trade_records_from_args(args)
    book = build_position_book(records, cash=args.cash, prices=prices)
    risk_report = check_holding_risk(
        book,
        stops=stops,
        max_exposure_pct=args.max_exposure_pct,
        max_position_pct=args.max_position_pct,
    )
    action_plan = build_position_action_plan(
        book,
        risk_report,
        stops=stops,
        max_exposure_pct=args.max_exposure_pct,
        max_position_pct=args.max_position_pct,
        target_exposure_pct=getattr(args, "target_exposure_pct", None),
    )
    if getattr(args, "record", False):
        append_position_action_plan_record(
            getattr(args, "log", Path("data/review/position_actions.jsonl")),
            action_plan,
            sqlite_path=getattr(args, "sqlite", None),
        )
    if getattr(args, "format", "json") == "markdown":
        text = "\n".join(render_position_action_plan_lines(action_plan))
    else:
        text = json.dumps(action_plan.to_dict(), ensure_ascii=False, indent=2)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_portfolio_exit_plan(args: argparse.Namespace) -> None:
    prices = parse_price_overrides(getattr(args, "price", []) or [])
    stops = parse_price_overrides(getattr(args, "stop", []) or [])
    targets = parse_price_overrides(getattr(args, "target", []) or [])
    invalidated = parse_kv_pairs(getattr(args, "invalidate", []) or [])
    records = _trade_records_from_args(args)
    book = build_position_book(records, cash=args.cash, prices=prices)
    if getattr(args, "lot_level", False):
        lot_book = build_lot_book(records, prices=prices, as_of=getattr(args, "plan_date", None)).to_dict()
        plan = build_lot_exit_plan(
            lot_book,
            stops=stops,
            targets=targets,
            invalidated=invalidated,
            max_holding_days=getattr(args, "max_holding_days", 20),
            time_stop_min_return_pct=getattr(args, "time_stop_min_return_pct", 0.0),
            profit_take_pct=getattr(args, "profit_take_pct", 0.5),
            plan_date=getattr(args, "plan_date", None),
        )
    else:
        plan = build_exit_plan(
            book,
            trade_records=records,
            stops=stops,
            targets=targets,
            invalidated=invalidated,
            max_position_pct=getattr(args, "max_position_pct", 0.2),
            max_holding_days=getattr(args, "max_holding_days", 20),
            time_stop_min_return_pct=getattr(args, "time_stop_min_return_pct", 0.0),
            profit_take_pct=getattr(args, "profit_take_pct", 0.5),
            plan_date=getattr(args, "plan_date", None),
        )
    if getattr(args, "record", False):
        append_exit_plan_record(
            getattr(args, "log", Path("data/review/exit_plans.jsonl")),
            plan,
            sqlite_path=getattr(args, "sqlite", None),
        )
    if getattr(args, "format", "json") == "markdown":
        text = render_exit_plan_markdown(plan)
    else:
        text = json.dumps(plan.to_dict(), ensure_ascii=False, indent=2)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def parse_price_overrides(items: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --price value: {item}. Expected symbol=price")
        symbol, value = item.split("=", 1)
        prices[str(symbol).strip().zfill(6)] = float(value)
    return prices


def parse_kv_pairs(items: list[str]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid query parameter: {item}. Expected key=value")
        key, value = item.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload

def run_optimize_experiments(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv)
    cases = load_experiment_cases(args.cases) if args.cases else preset_cases(args.preset)
    horizons = tuple(int(item.strip()) for item in args.horizons.split(",") if item.strip())
    results = run_parameter_experiments(
        frame,
        cases=cases,
        horizons=horizons,
        top=args.top,
        min_history=args.min_history,
    )
    payload = [result.to_dict() for result in results]
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))
    else:
        print(text)
    if args.report_output:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(
            ExperimentReport(
                preferred_horizon=args.recommend_horizon,
                min_count=args.recommend_min_count,
            ).render(payload),
            encoding="utf-8",
        )
        print(str(args.report_output))
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_payload = build_experiment_summary_payload(
            payload,
            preferred_horizon=args.recommend_horizon,
            min_count=args.recommend_min_count,
        )
        args.summary_output.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(str(args.summary_output))


def run_optimize_structure_calibration(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv)
    summary = run_structure_parameter_calibration(
        frame,
        base_params={
            "min_20d_return": args.min_20d_return,
            "min_volume_ratio": args.min_volume_ratio,
            "max_volume_ratio": args.max_volume_ratio,
            "max_atr_pct": args.max_atr_pct,
            "min_ma20_slope": args.min_ma20_slope,
            "max_close_ma20_gap": args.max_close_ma20_gap,
            "max_rsi": args.max_rsi,
            "min_traded_value": args.min_traded_value,
        },
        backtest_config=BacktestConfig(
            initial_cash=args.cash,
            max_position_pct=0.2,
            commission_rate=0.0003,
            slippage_rate=0.0005,
            buy_price_field=args.buy_price,
            execution_timing=args.execution_timing,
        ),
    )
    text = (
        render_calibration_markdown(summary)
        if args.format == "markdown"
        else json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_optimize_backtest_reliability(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv)
    strategies = _reliability_strategies_from_args(args)
    payload = build_backtest_reliability_audit(
        frame,
        strategies,
        BacktestReliabilityConfig(
            initial_cash=args.cash,
            buy_price_field=args.buy_price,
            execution_timing=args.execution_timing,
            train_ratio=args.train_ratio,
            regime_lookback=args.regime_lookback,
            bull_threshold=args.bull_threshold,
            bear_threshold=args.bear_threshold,
            min_rows_per_symbol=args.min_rows_per_symbol,
            max_stale_days=args.max_stale_days,
            as_of=args.as_of,
        ),
    )
    text = (
        render_backtest_reliability_markdown(payload)
        if args.format == "markdown"
        else json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def run_optimize_portfolio_calibration(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv)
    portfolio_config = StrategyPortfolioConfig.from_yaml(args.portfolio_config)
    summary = run_strategy_portfolio_calibration(
        frame,
        portfolio_config,
        variants=default_portfolio_calibration_variants(args.preset),
        cash=args.cash,
        buy_price=args.buy_price,
        execution_timing=args.execution_timing,
        rebalance_period=args.rebalance_period,
        max_positions=args.max_positions,
        min_history_days=args.min_history_days,
        train_ratio=args.train_ratio,
    )
    text = (
        render_strategy_portfolio_calibration_markdown(summary)
        if args.format == "markdown"
        else json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        print(str(args.output))
        return
    print(text)


def _reliability_strategies_from_args(args: argparse.Namespace) -> list[tuple[str, Any]]:
    strategies: list[tuple[str, Any]] = []
    for name in args.strategy or []:
        strategies.append((name, create_strategy(name)))
    for path in args.config or []:
        strategy = create_strategy_from_config(path)
        strategies.append((str(getattr(strategy, "config_name", "") or path.stem), strategy))
    if not strategies:
        strategies = [
            ("trend_breakout", create_strategy("trend_breakout")),
            ("strong_stock_screen", create_strategy("strong_stock_screen")),
        ]
    return strategies


def run_optimize_export_strategy(args: argparse.Namespace) -> None:
    summary = load_experiment_summary(args.summary)
    config = strategy_config_from_summary(summary, name=args.name, description=args.description)
    write_strategy_config(args.output, config)
    print(str(args.output))

def run_optimize_validate_strategy(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv) if args.csv else None
    result = validate_strategy_config(args.config, frame=frame, trade_plan_pressure=_trade_plan_pressure_from_args(args))
    payload = result.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if not result.ok:
        raise SystemExit(1)

def run_optimize_validate_strategies(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv) if args.csv else None
    pressure = _trade_plan_pressure_from_args(args)
    results = validate_strategy_directory(args.dir, frame=frame, trade_plan_pressure=pressure)
    payload = {
        "ok": all(item.ok for item in results),
        "count": len(results),
        "items": [item.to_dict() for item in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    if not payload["ok"]:
        raise SystemExit(1)

def run_optimize_promote_strategy(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv) if args.csv else None
    result = promote_strategy_from_summary(
        summary_path=args.summary,
        output_path=args.output,
        name=args.name,
        description=args.description,
        frame=frame,
        backtest=args.backtest,
        buy_price_field=args.buy_price,
        execution_timing=getattr(args, "execution_timing", "next_bar"),
        cash=args.cash,
        trade_plan_pressure=_trade_plan_pressure_from_args(args),
    )
    payload = result.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(text)
    if args.promotion_output:
        args.promotion_output.parent.mkdir(parents=True, exist_ok=True)
        args.promotion_output.write_text(text + "\n", encoding="utf-8")
        print(str(args.promotion_output))
    if args.promotion_log:
        persist_promotion_record(args.promotion_log, result, sqlite_path=getattr(args, "sqlite", None))
        print(str(args.promotion_log))
    elif getattr(args, "sqlite", None):
        SQLiteStore(args.sqlite).insert_strategy_promotion(result.to_dict())
        print(str(args.sqlite))
    if not result.ok:
        raise SystemExit(1)


def run_optimize_health(args: argparse.Namespace) -> None:
    print(json.dumps(_strategy_health_from_args(args), ensure_ascii=False, indent=2, default=str))


def run_optimize_rotation(args: argparse.Namespace) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    strategy_health = _strategy_health_from_args(args)
    constraint_summary = _constraint_summary_from_args(args, limit=max(int(args.limit), 1) * 3)
    promotion_summary = summarize_promotion_records(_promotion_records_from_args(args), limit=max(int(args.limit), 1))
    rotation = build_strategy_rotation(strategy_health, constraint_summary, promotion_summary, limit=args.limit)
    if args.format == "markdown":
        text = "\n".join([f"# Strategy Rotation {created_at}", "", *render_strategy_rotation_lines(rotation)])
        print(text)
        _write_rotation_outputs(args, text, "md", created_at)
        return
    text = json.dumps(
        {
            "created_at": created_at,
            "count": len(rotation),
            "items": rotation,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    print(text)
    _write_rotation_outputs(args, text, "json", created_at)


def _write_rotation_outputs(args: argparse.Namespace, text: str, suffix: str, created_at: str) -> None:
    output = getattr(args, "output", None)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
        print(str(output))
    snapshot_dir = getattr(args, "snapshot_dir", None)
    if snapshot_dir:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        stamp = created_at.replace(":", "").replace("-", "").split(".")[0].replace("+0000", "Z")
        path = snapshot_dir / f"rotation_{stamp}.{suffix}"
        path.write_text(text + "\n", encoding="utf-8")
        print(str(path))


def run_optimize_rotation_history(args: argparse.Namespace) -> None:
    snapshots = read_rotation_snapshots(args.snapshot_dir, limit=args.limit)
    summary = summarize_rotation_history(snapshots)
    if args.format == "markdown":
        text = "\n".join([*render_rotation_history_lines(summary), "", "## Snapshot Cards", "", *render_rotation_history_card_lines(summary)])
    else:
        text = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    print(text)
    if getattr(args, "output", None):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(str(args.output))


def _rotation_history_from_args(args: argparse.Namespace, limit: int = 20) -> dict | None:
    snapshot_dir = getattr(args, "rotation_snapshot_dir", None)
    if not snapshot_dir:
        return None
    snapshots = read_rotation_snapshots(snapshot_dir, limit=limit)
    return summarize_rotation_history(snapshots)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "screen":
        run_screen(args)
    elif args.command == "dragon":
        if args.dragon_command == "screen":
            run_dragon_screen(args)
        elif args.dragon_command == "check":
            run_dragon_check(args)
    elif args.command == "backtest":
        run_backtest(args)
    elif args.command == "workflow":
        if args.workflow_command == "premarket":
            run_workflow_premarket(args)
        elif args.workflow_command in {"trading-day", "daily"}:
            run_workflow_trading_day(args)
    elif args.command == "report":
        if args.report_command == "daily":
            run_daily_report(args)
        elif args.report_command == "weekly":
            run_weekly_report(args)
        elif args.report_command == "briefing":
            run_briefing_report(args)
        elif args.report_command == "premarket":
            run_premarket_report(args)
        elif args.report_command == "battle-plan":
            run_battle_plan_report(args)
        elif args.report_command == "cockpit":
            run_cockpit_report(args)
        elif args.report_command == "timeline":
            run_timeline_report(args)
        elif args.report_command == "assistant":
            run_assistant_report(args)
        elif args.report_command == "dragon":
            run_dragon_validation_report(args)
    elif args.command == "data":
        if args.data_command == "fetch-daily":
            run_data_fetch_daily(args)
        elif args.data_command == "fetch-batch":
            run_data_fetch_batch(args)
        elif args.data_command == "health":
            run_data_health(args)
        elif args.data_command == "repair-plan":
            run_data_repair_plan(args)
        elif args.data_command == "repair-execute":
            run_data_repair_execute(args)
        elif args.data_command == "universe":
            run_data_universe(args)
        elif args.data_command == "table":
            args.query = parse_kv_pairs(args.query)
            run_data_table(args)
        elif args.data_command == "provider-health":
            run_data_provider_health(args)
        elif args.data_command == "db":
            if args.db_command == "init":
                run_data_db_init(args)
            elif args.db_command == "import-universe":
                run_data_db_import_universe(args)
            elif args.db_command == "import-daily":
                run_data_db_import_daily(args)
            elif args.db_command == "import-batch-daily":
                run_data_db_import_batch_daily(args)
            elif args.db_command == "import-adjustment":
                run_data_db_import_adjustment(args)
            elif args.db_command == "import-batch-adjustment":
                run_data_db_import_batch_adjustment(args)
            elif args.db_command == "import-minute":
                run_data_db_import_minute(args)
            elif args.db_command == "import-batch-minute":
                run_data_db_import_batch_minute(args)
            elif args.db_command == "import-review":
                run_data_db_import_review(args)
            elif args.db_command == "screen":
                run_data_db_screen(args)
            elif args.db_command == "health":
                run_data_db_health(args)
            elif args.db_command == "doctor":
                run_data_db_doctor(args)
            elif args.db_command == "catalog":
                run_data_db_catalog(args)
            elif args.db_command == "sources":
                print(json.dumps(settings_from_args(args).data_sources.__dict__, ensure_ascii=False, indent=2))
            else:
                parser.error(f"Unknown data db command: {args.db_command}")
    elif args.command == "review":
        if args.review_command == "selections":
            run_review_selections(args)
        elif args.review_command == "trade-add":
            run_review_trade_add(args)
        elif args.review_command == "trade-list":
            run_review_trade_list(args)
        elif args.review_command == "trade-stats":
            run_review_trade_stats(args)
        elif args.review_command == "trade-audit":
            run_review_trade_audit(args)
        elif args.review_command == "execution-audit":
            run_review_execution_audit(args)
        elif args.review_command == "approval-audit":
            run_review_approval_audit(args)
        elif args.review_command == "approval-cooldown":
            run_review_approval_cooldown(args)
        elif args.review_command == "attribution":
            run_review_attribution(args)
        elif args.review_command == "attribution-policy":
            run_review_attribution_policy(args)
        elif args.review_command == "action-execution":
            run_review_action_execution(args)
        elif args.review_command == "exit-audit":
            run_review_exit_audit(args)
        elif args.review_command == "lot-stats":
            run_review_lot_stats(args)
        elif args.review_command == "lot-exit-audit":
            run_review_lot_exit_audit(args)
        elif args.review_command == "lifecycle":
            run_review_lifecycle(args)
        elif args.review_command == "lifecycle-history":
            run_review_lifecycle_history(args)
        elif args.review_command == "timeline-history":
            run_review_timeline_history(args)
        elif args.review_command == "timeline-watch":
            run_review_timeline_watch(args)
        elif args.review_command == "doctor":
            run_review_doctor(args)
        elif args.review_command == "approvals":
            run_review_approvals(args)
        elif args.review_command == "gates":
            run_review_gates(args)
        elif args.review_command == "exceptions":
            run_review_exceptions(args)
        elif args.review_command == "promotions":
            run_review_promotions(args)
        elif args.review_command == "constraints":
            run_review_constraints(args)
        elif args.review_command == "discipline":
            run_review_discipline(args)
        elif args.review_command == "discipline-adherence":
            run_review_discipline_adherence(args)
    elif args.command == "market":
        if args.market_command == "temperature":
            run_market_temperature(args)
        elif args.market_command == "sectors":
            run_market_sectors(args)
    elif args.command == "portfolio":
        if args.portfolio_command == "allocate":
            run_portfolio_allocate(args)
        elif args.portfolio_command == "precheck":
            run_portfolio_precheck(args)
        elif args.portfolio_command == "confirm":
            run_portfolio_confirm(args)
        elif args.portfolio_command == "tradable":
            run_portfolio_tradable(args)
        elif args.portfolio_command == "approve":
            run_portfolio_approve(args)
        elif args.portfolio_command == "plan":
            run_portfolio_plan(args)
        elif args.portfolio_command == "plan-batch":
            run_portfolio_plan_batch(args)
        elif args.portfolio_command == "positions":
            run_portfolio_positions(args)
        elif args.portfolio_command == "lots":
            run_portfolio_lots(args)
        elif args.portfolio_command == "lifecycle":
            run_portfolio_lifecycle(args)
        elif args.portfolio_command == "risk":
            run_portfolio_risk(args)
        elif args.portfolio_command == "actions":
            run_portfolio_actions(args)
        elif args.portfolio_command == "exit-plan":
            run_portfolio_exit_plan(args)
    elif args.command == "optimize":
        if args.optimize_command == "experiments":
            run_optimize_experiments(args)
        elif args.optimize_command == "structure-calibration":
            run_optimize_structure_calibration(args)
        elif args.optimize_command == "backtest-reliability":
            run_optimize_backtest_reliability(args)
        elif args.optimize_command == "portfolio-calibration":
            run_optimize_portfolio_calibration(args)
        elif args.optimize_command == "export-strategy":
            run_optimize_export_strategy(args)
        elif args.optimize_command == "validate-strategy":
            run_optimize_validate_strategy(args)
        elif args.optimize_command == "validate-strategies":
            run_optimize_validate_strategies(args)
        elif args.optimize_command == "promote-strategy":
            run_optimize_promote_strategy(args)
        elif args.optimize_command == "health":
            run_optimize_health(args)
        elif args.optimize_command == "rotation":
            run_optimize_rotation(args)
        elif args.optimize_command == "rotation-history":
            run_optimize_rotation_history(args)
    else:
        parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()


