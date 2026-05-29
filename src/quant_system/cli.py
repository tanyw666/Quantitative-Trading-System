from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from quant_system.config.settings import load_settings
from quant_system.config.settings import SystemSettings
from quant_system.backtest.engine import BacktestConfig, BacktestEngine
from quant_system.data.cache import fetch_daily_to_cache, load_daily_cache, save_daily_cache
from quant_system.data.csv_source import read_ohlcv_csv
from quant_system.data.dataset import load_ohlcv_dataset
from quant_system.data.health import build_ohlcv_repair_plan, check_ohlcv_health
from quant_system.data.manifest import CacheManifest, CacheManifestEntry
from quant_system.data.providers import fetch_table_with_fallback, fetch_with_fallback
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
from quant_system.portfolio.journal import (
    TradeJournal,
    TradeJournalEntry,
    summarize_discipline_exceptions,
    summarize_gate_journal,
    summarize_trade_journal,
)
from quant_system.portfolio.positions import build_position_book
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
from quant_system.reports.strategy_rotation import build_strategy_rotation, render_strategy_rotation_lines
from quant_system.reports.rotation_history import (
    read_rotation_snapshots,
    render_rotation_history_card_lines,
    render_rotation_history_lines,
    summarize_rotation_history,
)
from quant_system.reports.pretrade import render_precheck_markdown
from quant_system.reports.premarket import PremarketReport, PremarketReportInput
from quant_system.risk.pretrade import run_pretrade_check
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
    screen.add_argument("--settings", type=Path, help="System settings YAML")
    screen.add_argument("--record", action="store_true", help="Record selections")
    screen.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    screen.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    screen.add_argument("--top", type=int, help="Limit to top N results")
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
    backtest.add_argument("--buy-price", choices=["close", "open"], default="close", help="Backtest buy price")
    add_dragon_gate_arg(backtest)
    add_dragon_entry_model_arg(backtest)

    workflow = subparsers.add_parser("workflow", help="Operational workflows")
    workflow_sub = workflow.add_subparsers(dest="workflow_command", required=True)
    workflow_premarket = workflow_sub.add_parser("premarket", help="Run the premarket health and report workflow")
    add_dataset_args(workflow_premarket)
    workflow_premarket.add_argument("--output", type=Path, default=Path("reports/premarket.md"))
    workflow_premarket.add_argument("--summary-output", type=Path, help="Optional JSON workflow summary output")
    workflow_premarket.add_argument("--strategy", default="strong_stock_screen")
    workflow_premarket.add_argument("--config", type=Path, help="Strategy YAML config")
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

    report = subparsers.add_parser("report", help="Generate reports")
    report_sub = report.add_subparsers(dest="report_command", required=True)
    daily = report_sub.add_parser("daily", help="Generate daily markdown report")
    daily.add_argument("--output", type=Path, default=Path("reports/daily.md"))
    add_dataset_args(daily)
    daily.add_argument("--strategy", default="strong_stock_screen")
    daily.add_argument("--config", type=Path, help="Strategy YAML config")
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
    weekly.add_argument("--settings", type=Path, help="System settings YAML")
    weekly.add_argument("--experiment-summary", type=Path, help="Experiment summary JSON")
    weekly.add_argument("--promotion-log", type=Path, default=Path("data/review/promotions.jsonl"), help="Strategy promotion JSONL")
    weekly.add_argument("--constraint-log", type=Path, default=Path("data/review/strategy_constraints.jsonl"))
    add_discipline_record_args(weekly)
    weekly.add_argument("--rotation-snapshot-dir", type=Path, default=Path("reports/rotation_snapshots"))
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
    briefing.add_argument("--cash", type=float, default=100000)
    briefing.add_argument("--top", type=int, default=5)
    add_sector_context_args(briefing)
    briefing.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    briefing.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    briefing.add_argument("--max-exposure-pct", type=float, default=0.8)
    briefing.add_argument("--max-position-pct", type=float, default=0.2)

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
    add_sector_context_args(premarket)
    premarket.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    premarket.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    premarket.add_argument("--max-exposure-pct", type=float, default=0.8)
    premarket.add_argument("--max-position-pct", type=float, default=0.2)

    dragon_report = report_sub.add_parser("dragon", help="Generate dragon validation report")
    dragon_report.add_argument("--output", type=Path, default=Path("reports/dragon_validation.md"))
    add_dataset_args(dragon_report)
    dragon_report.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    dragon_report.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    dragon_report.add_argument("--horizons", default="1,3,5")
    dragon_report.add_argument("--cash", type=float, default=100000)
    dragon_report.add_argument("--buy-price", choices=["close", "open"], default="close", help="Backtest buy price")
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

    db_screen = db_sub.add_parser("screen", help="Run screening on SQLite data")
    db_screen.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_screen.add_argument("--strategy", default="strong_stock_screen")
    db_screen.add_argument("--config", type=Path, help="Strategy YAML config")
    db_screen.add_argument("--settings", type=Path, help="System settings YAML")
    db_screen.add_argument("--top", type=int, help="Limit to top N results")
    add_sector_context_args(db_screen)
    add_dragon_gate_arg(db_screen)
    add_dragon_entry_model_arg(db_screen)

    db_health = db_sub.add_parser("health", help="Check SQLite daily bars health")
    db_health.add_argument("--db-path", type=Path, default=Path("data/quant.sqlite"))
    db_health.add_argument("--min-rows", type=int, default=30)
    db_health.add_argument("--max-stale-days", type=int)
    db_health.add_argument("--as-of", help="Health check reference date, e.g. 2026-05-28")
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

    positions = portfolio_sub.add_parser("positions", help="Rebuild current positions from trade journal")
    positions.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    positions.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    positions.add_argument("--cash", type=float, default=100000)
    positions.add_argument("--price", action="append", default=[], help="Current price, symbol=price")

    holding_risk = portfolio_sub.add_parser("risk", help="Check holding risk")
    holding_risk.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    holding_risk.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
    holding_risk.add_argument("--cash", type=float, default=100000)
    holding_risk.add_argument("--price", action="append", default=[], help="Current price, symbol=price")
    holding_risk.add_argument("--stop", action="append", default=[], help="Stop price, symbol=price")
    holding_risk.add_argument("--max-exposure-pct", type=float, default=0.8)
    holding_risk.add_argument("--max-position-pct", type=float, default=0.2)

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
    export_strategy = optimize_sub.add_parser("export-strategy", help="Export strategy YAML from experiment summary")
    export_strategy.add_argument("--summary", type=Path, required=True, help="Experiment summary JSON")
    export_strategy.add_argument("--output", type=Path, required=True, help="Strategy YAML output path")
    export_strategy.add_argument("--name", help="Optional strategy name override")
    export_strategy.add_argument("--description", help="Optional strategy description override")
    validate_strategy = optimize_sub.add_parser("validate-strategy", help="Validate one strategy YAML")
    validate_strategy.add_argument("--config", type=Path, required=True, help="Strategy YAML path")
    validate_strategy.add_argument("--csv", type=Path, help="Optional OHLCV CSV for a smoke test")
    validate_strategies = optimize_sub.add_parser("validate-strategies", help="Validate a directory of strategy YAML files")
    validate_strategies.add_argument("--dir", type=Path, default=Path("configs/strategies"), help="Strategy YAML directory")
    validate_strategies.add_argument("--csv", type=Path, help="Optional OHLCV CSV for a smoke test")
    promote_strategy = optimize_sub.add_parser("promote-strategy", help="Export a promoted strategy and optionally backtest it")
    promote_strategy.add_argument("--summary", type=Path, required=True, help="Experiment summary JSON")
    promote_strategy.add_argument("--output", type=Path, required=True, help="Strategy YAML output path")
    promote_strategy.add_argument("--name", help="Optional strategy name override")
    promote_strategy.add_argument("--description", help="Optional strategy description override")
    promote_strategy.add_argument("--csv", type=Path, help="Optional OHLCV CSV for a smoke backtest")
    promote_strategy.add_argument("--backtest", action="store_true", help="Run one backtest after promotion")
    promote_strategy.add_argument("--buy-price", choices=["close", "open"], default="close", help="Backtest buy price")
    promote_strategy.add_argument("--cash", type=float, default=100000)
    promote_strategy.add_argument("--promotion-output", type=Path, help="Optional promotion result JSON")
    promote_strategy.add_argument("--promotion-log", type=Path, help="Optional promotion history JSONL")
    promote_strategy.add_argument("--sqlite", type=Path, help="Optional SQLite store path")
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


def add_dragon_gate_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--entry-gate",
        choices=["all", "pass-watch", "pass"],
        default="all",
        help="浠?dragon_leader 浣跨敤锛氭寜杩涘満闂搁棬杩囨护淇″彿",
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
    return source_from_args(args, attr, default)

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

def run_screen(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    frame = limit_recent_history(frame, getattr(args, "lookback_days", None))
    frame = prefilter_dragon_universe(frame, args.strategy, getattr(args, "prefilter_symbols", None))
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    results = strategy.screen(frame)
    results = enrich_and_score_candidates(
        frame,
        results,
        settings.scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.sector_top,
        only_top_sectors=args.only_top_sectors,
    )
    if args.top:
        results = results.head(args.top)
    rows = results.to_dict(orient="records")
    if args.record:
        SelectionTracker(args.tracker, sqlite_path=getattr(args, "sqlite", None)).record_many(records_from_selection(strategy.name, rows))
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
    engine = BacktestEngine(BacktestConfig(initial_cash=args.cash, buy_price_field=args.buy_price))
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
        strategy = strategy_from_args(args)
        args._resolved_strategy = strategy
        settings = settings_from_args(args)
        current_strategy_health = _current_strategy_health(args)
        selected_frame = strategy.screen(frame)
        selected_frame = enrich_and_score_candidates(
            frame,
            selected_frame,
            settings.scoring.weights,
            sector_column=args.sector_column,
            sector_top=args.sector_top,
            only_top_sectors=args.only_top_sectors,
        )
        if args.top:
            selected_frame = selected_frame.head(args.top)
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
        SelectionTracker(args.tracker, sqlite_path=getattr(args, "sqlite", None)).record_many(records_from_selection(strategy.name, selected))
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
        candidates = strategy.screen(frame)
        if not candidates.empty:
            from quant_system.screening.scoring import score_candidates

            candidates = score_candidates(candidates, settings.scoring.weights)
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
    gate_review = summarize_gate_journal(trade_records, limit=10)
    discipline_summary = _discipline_summary_from_args(args, limit=10)
    discipline_adherence = _discipline_adherence_summary_from_args(args, limit=10)
    experiment_summary = None
    if args.experiment_summary and args.experiment_summary.exists():
        experiment_summary = json.loads(args.experiment_summary.read_text(encoding="utf-8"))
    promotion_summary = summarize_promotion_records(_promotion_records_from_args(args), limit=10)
    strategy_health = _strategy_health_from_args(args)
    constraint_summary = _constraint_summary_from_args(args, limit=10)
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
    current_candidates = strategy.screen(frame)
    current_candidates = enrich_and_score_candidates(
        frame,
        current_candidates,
        settings_from_args(args).scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.sector_top,
        only_top_sectors=args.only_top_sectors,
    )
    if args.top:
        current_candidates = current_candidates.head(args.top)
    backtest_result = BacktestEngine(
        BacktestConfig(initial_cash=args.cash, buy_price_field=args.buy_price)
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
    candidates = strategy.screen(frame)
    candidates = enrich_and_score_candidates(
        frame,
        candidates,
        settings.scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.top,
        only_top_sectors=False,
    )
    if args.top:
        candidates = candidates.head(args.top)

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
    position_book = build_position_book(trade_records, cash=args.cash, prices=prices).to_dict()
    holding_risk = check_holding_risk(
        build_position_book(trade_records, cash=args.cash, prices=prices),
        stops=stops,
        max_exposure_pct=args.max_exposure_pct,
        max_position_pct=args.max_position_pct,
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
            holding_risk=holding_risk,
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


def run_premarket_report(args: argparse.Namespace, *, print_path: bool = True, context: dict | None = None) -> None:
    context = context or _premarket_context_from_args(args)
    content = PremarketReport().render(
        PremarketReportInput(
            title="A-share Premarket Report",
            market_temperature=context["market_temperature"],
            market_context=context["market_context"],
            data_health=context["data_health"],
            candidates=context["candidates"],
            allocation_plan=context["allocation_plan"],
            pretrade_checks=context["pretrade_checks"],
            position_book=context["position_book"],
            holding_risk=context["holding_risk"],
            strategy_health=context["strategy_health"],
            constraint_summary=context["constraint_summary"],
            strategy_rotation=context["strategy_rotation"],
            rotation_history=context["rotation_history"],
            gate_review=context.get("gate_review"),
            trade_stats=context.get("trade_stats"),
            discipline_summary=context.get("discipline_summary"),
            discipline_adherence=context.get("discipline_adherence"),
        )
    )
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


def _premarket_context_from_args(
    args: argparse.Namespace,
    *,
    frame: pd.DataFrame | None = None,
    data_health: dict | None = None,
) -> dict:
    frame = frame if frame is not None else load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    current_strategy_health = _current_strategy_health(args)
    candidates = strategy.screen(frame)
    candidates = enrich_and_score_candidates(
        frame,
        candidates,
        settings.scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.sector_top,
        only_top_sectors=False,
    )
    if args.top:
        candidates = candidates.head(args.top)
    market_temperature = calculate_market_temperature(frame, candidates).to_dict()
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
    position_book = build_position_book(trade_records, cash=args.cash, prices=prices).to_dict()
    holding_risk = check_holding_risk(
        build_position_book(trade_records, cash=args.cash, prices=prices),
        stops=stops,
        max_exposure_pct=args.max_exposure_pct,
        max_position_pct=args.max_position_pct,
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
        max_positions=max_positions,
    )
    return {
        "market_temperature": market_temperature,
        "market_context": market_context,
        "data_health": data_health,
        "candidates": candidates.to_dict(orient="records"),
        "allocation_plan": allocation_plan,
        "pretrade_checks": pretrade_checks,
        "position_book": position_book,
        "holding_risk": holding_risk,
        "strategy_health": strategy_health,
        "constraint_summary": constraint_summary,
        "strategy_rotation": strategy_rotation,
        "rotation_history": rotation_history,
        "gate_review": gate_review,
        "trade_stats": trade_stats,
        "discipline_summary": discipline_summary,
        "discipline_adherence": discipline_adherence,
    }


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
    except FileNotFoundError as exc:
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

    context = _premarket_context_from_args(args, frame=frame, data_health=health)
    gate = _workflow_execution_gate(health, repair_plan, context)
    summary["gate"] = gate
    summary["steps"].append({"name": "execution_gate", "status": gate["status"], "summary": gate})
    if gate["status"] == "block":
        summary["status"] = "block" if summary["status"] != "fail" else "fail"
    elif gate["status"] == "warn" and summary["status"] == "ok":
        summary["status"] = "warn"

    run_premarket_report(args, print_path=False, context=context)
    summary["steps"].append({"name": "premarket_report", "status": "ok", "path": str(args.output)})
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


def _workflow_execution_gate(health: dict, repair_plan: dict, context: dict) -> dict:
    reasons: list[str] = []
    status = "pass"
    pretrade_checks = list(context.get("pretrade_checks", []) or [])
    pretrade_statuses = [str(item.get("status", "") or "") for item in pretrade_checks]
    holding_status = str((context.get("holding_risk") or {}).get("status", "pass") or "pass")
    regime = str((context.get("market_temperature") or {}).get("regime", "") or "")

    if health.get("status") == "fail":
        status = "block"
        reasons.append("数据健康检查失败")
    if "block" in pretrade_statuses:
        status = "block"
        reasons.append("交易前预检存在阻断项")
    if holding_status == "block":
        status = "block"
        reasons.append("持仓风险存在阻断项")
    if regime in {"frozen", "empty"}:
        status = "block"
        reasons.append(f"市场状态为 {regime}")

    if status != "block":
        if health.get("status") == "warn":
            status = "warn"
            reasons.append("数据健康存在预警")
        if repair_plan.get("status") == "action_needed":
            status = "warn"
            reasons.append("缓存/历史数据需要修复")
        if "warn" in pretrade_statuses:
            status = "warn"
            reasons.append("交易前预检存在预警项")
        if holding_status == "warn":
            status = "warn"
            reasons.append("持仓风险存在预警项")
        if regime == "cold":
            status = "warn"
            reasons.append("市场温度偏冷")

    message = {
        "pass": "可进入计划交易，但正式买入前仍需重跑单票 precheck。",
        "warn": "只允许计划内确认单，禁止追高加仓；先处理预警项。",
        "block": "禁止新开仓，先处理阻断项。",
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
    except FileNotFoundError as exc:
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
    except FileNotFoundError as exc:
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
    except FileNotFoundError as exc:
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
    candidates = strategy.screen(frame)
    candidates = enrich_and_score_candidates(
        frame,
        candidates,
        settings.scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.sector_top,
        only_top_sectors=args.only_top_sectors,
    )
    if args.top:
        candidates = candidates.head(args.top)
    print(json.dumps(candidates.to_dict(orient="records"), ensure_ascii=False, indent=2, default=str))

def run_data_db_health(args: argparse.Namespace) -> None:
    store = SQLiteStore(args.db_path)
    frame = store.read_daily_bars()
    if frame.empty:
        print(json.dumps({"status": "fail", "rows": 0, "symbols": 0, "issues": [{"name": "empty", "status": "fail", "message": "Database daily_bars table is empty."}]}, ensure_ascii=False, indent=2))
        return
    report = check_ohlcv_health(frame, min_rows_per_symbol=args.min_rows, max_stale_days=args.max_stale_days, as_of=args.as_of)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))

def run_data_db_catalog(args: argparse.Namespace) -> None:
    raise NotImplementedError("data db catalog is not implemented")

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
    if gate.get("status") in {"warn", "block"}:
        tag = f"gate-{gate['status']}"
        if tag not in tags:
            tags.append(tag)
    if getattr(args, "discipline_exception", False) and "discipline-exception" not in tags:
        tags.append("discipline-exception")
    entry = TradeJournalEntry(
        date=args.date,
        symbol=str(args.symbol).zfill(6),
        side=args.side.upper(),
        price=args.price,
        quantity=args.quantity,
        reason=args.reason,
        name=args.name,
        strategy=args.strategy,
        market_regime=args.market_regime,
        planned_pct=args.planned_pct,
        actual_pct=args.actual_pct,
        planned_price=args.planned_price,
        stop_price=args.stop_price,
        target_price=args.target_price,
        tags=tags,
        mistake_type=args.mistake_type,
        review=args.review,
        gate_status=str(gate.get("status", "")),
        gate_message=str(gate.get("message", "")),
        gate_reasons=list(gate.get("reasons", []) or []),
        workflow_summary=str(getattr(args, "workflow_summary", "") or ""),
        discipline_exception=bool(getattr(args, "discipline_exception", False)),
        exception_reason=str(getattr(args, "exception_reason", "") or ""),
    )
    TradeJournal(args.journal, sqlite_path=getattr(args, "sqlite", None)).add(entry)
    print(json.dumps(entry.to_record(), ensure_ascii=False, indent=2))


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


def _trade_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_trade_records(args.sqlite)
    return TradeJournal(getattr(args, "journal", None) or Path("data/review/trades.jsonl")).list()


def _discipline_records_from_args(args: argparse.Namespace) -> list[dict]:
    if getattr(args, "sqlite", None):
        return _sqlite_discipline_records(args.sqlite)
    path = getattr(args, "discipline_log", None) or getattr(args, "log", None) or Path("data/review/discipline.jsonl")
    return read_discipline_records(path)


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


def _strategy_health_from_args(args: argparse.Namespace) -> list[dict]:
    if not getattr(args, "sqlite", None):
        return []
    constraint_records = _sqlite_constraint_records(args.sqlite)
    policy = settings_from_args(args).risk.constraint_policy
    return [
        apply_constraint_policy_to_health(item.to_dict(), constraint_records, **policy.kwargs_for(item.strategy))
        for item in summarize_strategy_health(
            _sqlite_selection_records(args.sqlite),
            _sqlite_trade_records(args.sqlite),
            _sqlite_promotion_records(args.sqlite),
        )
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
        **settings_from_args(args).risk.constraint_policy.kwargs_for(strategy_name),
    )


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
        return _sqlite_constraint_records(sqlite_path)
    path = getattr(args, "constraint_log", None) or Path("data/review/strategy_constraints.jsonl")
    return read_constraint_audit_records(path)


def _constraint_policy_kwargs_from_args(args: argparse.Namespace) -> dict:
    policy = settings_from_args(args).risk.constraint_policy
    return policy.kwargs_for(str(getattr(args, "strategy", "") or ""))


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
    candidates = strategy.screen(frame)
    candidates = enrich_and_score_candidates(
        frame,
        candidates,
        settings.scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.sector_top,
        only_top_sectors=False,
    )
    if args.top:
        candidates = candidates.head(args.top)
    temperature = calculate_market_temperature(frame, candidates)
    print(json.dumps(temperature.to_dict(), ensure_ascii=False, indent=2))

def run_market_sectors(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    candidates = strategy.screen(frame)
    candidates = enrich_and_score_candidates(
        frame,
        candidates,
        settings.scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.top,
        only_top_sectors=False,
    )
    sectors = calculate_sector_strength(frame, candidates, sector_column=args.sector_column, top=args.top)
    print(json.dumps(sectors.to_dict(orient="records"), ensure_ascii=False, indent=2, default=str))

def run_portfolio_allocate(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    args._resolved_strategy = strategy
    settings = settings_from_args(args)
    candidates = strategy.screen(frame)
    candidates = enrich_and_score_candidates(
        frame,
        candidates,
        settings.scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.sector_top,
        only_top_sectors=args.only_top_sectors,
    )
    if args.top:
        candidates = candidates.head(args.top)
    temperature = calculate_market_temperature(frame, candidates).to_dict()
    plan = build_allocation_plan(
        candidates,
        temperature,
        cash=args.cash,
        max_positions=args.top,
        regime_exposure=settings.risk.regime_exposure,
        cap_by_risk=settings.risk.cap_by_risk,
        strategy_health=_current_strategy_health(args),
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
    candidates = strategy.screen(frame)
    candidates = enrich_and_score_candidates(
        frame,
        candidates,
        settings.scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.sector_top,
        only_top_sectors=args.only_top_sectors,
    )
    if args.top:
        candidates = candidates.head(args.top)
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
        strategy_health=_current_strategy_health(args),
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

def run_portfolio_positions(args: argparse.Namespace) -> None:
    prices = parse_price_overrides(args.price)
    records = _trade_records_from_args(args)
    book = build_position_book(records, cash=args.cash, prices=prices)
    print(json.dumps(book.to_dict(), ensure_ascii=False, indent=2))

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

def run_optimize_export_strategy(args: argparse.Namespace) -> None:
    summary = load_experiment_summary(args.summary)
    config = strategy_config_from_summary(summary, name=args.name, description=args.description)
    write_strategy_config(args.output, config)
    print(str(args.output))

def run_optimize_validate_strategy(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv) if args.csv else None
    result = validate_strategy_config(args.config, frame=frame)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, default=str))
    if not result.ok:
        raise SystemExit(1)

def run_optimize_validate_strategies(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv) if args.csv else None
    results = validate_strategy_directory(args.dir, frame=frame)
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
        cash=args.cash,
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
        text = "\n".join([f"生成时间：{created_at}", "", *render_strategy_rotation_lines(rotation)])
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
        text = "\n".join([*render_rotation_history_lines(summary), "", "## 历史卡片", "", *render_rotation_history_card_lines(summary)])
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
    elif args.command == "report":
        if args.report_command == "daily":
            run_daily_report(args)
        elif args.report_command == "weekly":
            run_weekly_report(args)
        elif args.report_command == "briefing":
            run_briefing_report(args)
        elif args.report_command == "premarket":
            run_premarket_report(args)
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
            elif args.db_command == "screen":
                run_data_db_screen(args)
            elif args.db_command == "health":
                run_data_db_health(args)
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
        elif args.portfolio_command == "positions":
            run_portfolio_positions(args)
        elif args.portfolio_command == "risk":
            run_portfolio_risk(args)
    elif args.command == "optimize":
        if args.optimize_command == "experiments":
            run_optimize_experiments(args)
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


