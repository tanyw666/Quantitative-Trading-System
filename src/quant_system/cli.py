from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from quant_system.config.settings import load_settings
from quant_system.backtest.engine import BacktestConfig, BacktestEngine
from quant_system.data.cache import fetch_daily_to_cache, load_daily_cache, save_daily_cache
from quant_system.data.csv_source import read_ohlcv_csv
from quant_system.data.dataset import load_ohlcv_dataset
from quant_system.data.health import check_ohlcv_health
from quant_system.data.manifest import CacheManifest, CacheManifestEntry
from quant_system.data.providers import fetch_with_fallback
from quant_system.data.universe import read_universe
from quant_system.data.universe_builder import UniverseBuildOptions, fetch_akshare_universe, filter_universe, save_universe
from quant_system.market.temperature import calculate_market_temperature
from quant_system.market.sectors import (
    annotate_candidates_with_sector_strength,
    calculate_sector_strength,
    filter_candidates_by_top_sectors,
)
from quant_system.optimizer.experiments import load_experiment_cases, preset_cases, run_parameter_experiments
from quant_system.optimizer.selection_validation import (
    summarize_forward_returns,
    summarize_forward_returns_by,
    validate_selection_file,
)
from quant_system.portfolio.journal import TradeJournal, TradeJournalEntry, summarize_trade_journal
from quant_system.portfolio.positions import build_position_book
from quant_system.portfolio.risk_check import check_holding_risk
from quant_system.reports.briefing import BriefingInput, BriefingReport
from quant_system.portfolio.selection_tracker import SelectionRecord, SelectionTracker
from quant_system.reports.daily import DailyReport, DailyReportInput
from quant_system.reports.dragon import DragonValidationInput, DragonValidationReport
from quant_system.reports.experiments import ExperimentReport, build_experiment_summary_payload
from quant_system.reports.weekly import WeeklyReport, WeeklyReportInput
from quant_system.risk.pretrade import run_pretrade_check
from quant_system.risk.sizing import build_allocation_plan
from quant_system.screening.scoring import score_candidates
from quant_system.strategies.dragon_leader import latest_dragon_diagnostics
from quant_system.strategies.registry import create_strategy, create_strategy_from_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quant-system",
        description="A股量化研究、选股、回测和复盘工具",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    screen = subparsers.add_parser("screen", help="运行选股策略")
    add_dataset_args(screen)
    screen.add_argument("--strategy", default="strong_stock_screen")
    screen.add_argument("--config", type=Path, help="YAML 条件树策略配置")
    screen.add_argument("--settings", type=Path, help="系统设置 YAML，覆盖评分和仓位规则")
    screen.add_argument("--record", action="store_true", help="将选股结果写入追踪日志")
    screen.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    screen.add_argument("--top", type=int, help="只输出评分最高的前 N 只")
    add_sector_context_args(screen)

    dragon = subparsers.add_parser("dragon", help="龙头战法工具")
    dragon_sub = dragon.add_subparsers(dest="dragon_command", required=True)
    dragon_screen = dragon_sub.add_parser("screen", help="筛选连板/弱转强龙头候选")
    add_dataset_args(dragon_screen)
    dragon_screen.add_argument("--settings", type=Path, help="系统设置 YAML，覆盖评分和仓位规则")
    dragon_screen.add_argument("--record", action="store_true", help="将选股结果写入追踪日志")
    dragon_screen.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    dragon_screen.add_argument("--top", type=int, help="只输出评分最高的前 N 只")
    add_dragon_gate_arg(dragon_screen)
    add_dragon_entry_model_arg(dragon_screen)
    add_sector_context_args(dragon_screen)
    dragon_check = dragon_sub.add_parser("check", help="诊断单票龙头结构")
    add_dataset_args(dragon_check)
    dragon_check.add_argument("--symbol", required=True)

    backtest = subparsers.add_parser("backtest", help="运行策略回测")
    backtest.add_argument("--csv", type=Path, required=True, help="OHLCV CSV 文件路径")
    backtest.add_argument("--strategy", default="trend_breakout")
    backtest.add_argument("--config", type=Path, help="YAML 条件树策略配置")
    backtest.add_argument("--cash", type=float, default=100000)
    backtest.add_argument("--buy-price", choices=["close", "open"], default="close", help="回测买入成交基准价")
    add_dragon_gate_arg(backtest)
    add_dragon_entry_model_arg(backtest)

    report = subparsers.add_parser("report", help="生成复盘报告")
    report_sub = report.add_subparsers(dest="report_command", required=True)
    daily = report_sub.add_parser("daily", help="生成 Markdown 日报")
    daily.add_argument("--output", type=Path, default=Path("reports/daily.md"))
    add_dataset_args(daily)
    daily.add_argument("--strategy", default="strong_stock_screen")
    daily.add_argument("--config", type=Path, help="YAML 条件树策略配置")
    daily.add_argument("--settings", type=Path, help="系统设置 YAML，覆盖评分和仓位规则")
    daily.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    daily.add_argument("--top", type=int, help="日报只保留评分最高的前 N 只")
    daily.add_argument("--cash", type=float, default=100000, help="用于仓位建议的账户资金")
    daily.add_argument("--max-positions", type=int, default=5, help="仓位建议最多分配几只候选")
    add_sector_context_args(daily)

    weekly = report_sub.add_parser("weekly", help="生成 Markdown 周报")
    weekly.add_argument("--output", type=Path, default=Path("reports/weekly.md"))
    weekly.add_argument("--csv", type=Path, help="包含后续行情的 OHLCV CSV，用于市场温度和选股后验")
    weekly.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    weekly.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    weekly.add_argument("--horizons", default="1,3,5")
    weekly.add_argument("--strategy", default="strong_stock_screen")
    weekly.add_argument("--config", type=Path, help="YAML 条件树策略配置")
    weekly.add_argument("--settings", type=Path, help="系统设置 YAML，覆盖评分和仓位规则")
    weekly.add_argument("--experiment-summary", type=Path, help="策略实验摘要 JSON，来自 optimize experiments --summary-output")
    weekly.add_argument("--note", action="append", default=[], help="下周改进事项，可重复传入")

    briefing = report_sub.add_parser("briefing", help="生成盘前/盘中作战简报")
    briefing.add_argument("--output", type=Path, default=Path("reports/briefing.md"))
    add_dataset_args(briefing)
    briefing.add_argument("--strategy", default="strong_stock_screen")
    briefing.add_argument("--config", type=Path, help="YAML 条件树策略配置")
    briefing.add_argument("--settings", type=Path, help="系统设置 YAML，覆盖评分和仓位规则")
    briefing.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    briefing.add_argument("--cash", type=float, default=100000)
    briefing.add_argument("--top", type=int, default=5)
    add_sector_context_args(briefing)
    briefing.add_argument("--price", action="append", default=[], help="当前价，格式 symbol=price，可重复传入")
    briefing.add_argument("--stop", action="append", default=[], help="止损价，格式 symbol=price，可重复传入")
    briefing.add_argument("--max-exposure-pct", type=float, default=0.8)
    briefing.add_argument("--max-position-pct", type=float, default=0.2)

    dragon_report = report_sub.add_parser("dragon", help="生成龙头战法双轨验证报告")
    dragon_report.add_argument("--output", type=Path, default=Path("reports/dragon_validation.md"))
    dragon_report.add_argument("--csv", type=Path, required=True, help="OHLCV CSV 文件路径")
    dragon_report.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    dragon_report.add_argument("--horizons", default="1,3,5")
    dragon_report.add_argument("--cash", type=float, default=100000)
    dragon_report.add_argument("--buy-price", choices=["close", "open"], default="close", help="回测买入成交基准价")
    add_dragon_gate_arg(dragon_report)
    add_dragon_entry_model_arg(dragon_report)

    data = subparsers.add_parser("data", help="行情数据工具")
    data_sub = data.add_subparsers(dest="data_command", required=True)
    fetch_daily = data_sub.add_parser("fetch-daily", help="拉取 A 股日线并写入本地缓存")
    fetch_daily.add_argument("--symbol", required=True, help="股票代码，例如 000001")
    fetch_daily.add_argument("--start", required=True, help="开始日期，例如 20240101")
    fetch_daily.add_argument("--end", required=True, help="结束日期，例如 20240527")
    fetch_daily.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"], help="复权方式")
    fetch_daily.add_argument("--cache-dir", type=Path, default=Path("data/cache/daily"))
    fetch_daily.add_argument("--source", default="auto", choices=["auto", "mootdx", "akshare"], help="行情源")

    fetch_batch = data_sub.add_parser("fetch-batch", help="按股票池批量刷新日线缓存")
    fetch_batch.add_argument("--universe", type=Path, required=True, help="股票池 CSV，包含 symbol/name")
    fetch_batch.add_argument("--start", required=True, help="开始日期，例如 20240101")
    fetch_batch.add_argument("--end", required=True, help="结束日期，例如 20240527")
    fetch_batch.add_argument("--adjust", default="qfq", choices=["", "qfq", "hfq"], help="复权方式")
    fetch_batch.add_argument("--cache-dir", type=Path, default=Path("data/cache/daily"))
    fetch_batch.add_argument("--manifest", type=Path, default=Path("data/cache/manifest.jsonl"))
    fetch_batch.add_argument("--source", default="auto", choices=["auto", "mootdx", "akshare"], help="行情源")
    fetch_batch.add_argument("--limit", type=int, help="最多更新多少只，调试用")
    fetch_batch.add_argument("--refresh", action="store_true", help="即使缓存已存在也强制刷新")

    health = data_sub.add_parser("health", help="检查 OHLCV 行情数据健康状态")
    add_dataset_args(health)
    health.add_argument("--strict", action="store_true", help="股票池中任一缓存缺失则报错")
    health.add_argument("--min-rows", type=int, default=30, help="每只股票最少历史行数")
    health.add_argument("--max-stale-days", type=int, help="允许最新数据滞后的最大自然日")
    health.add_argument("--as-of", help="健康检查基准日期，例如 2026-05-28")

    universe = data_sub.add_parser("universe", help="生成 A 股股票池")
    universe.add_argument("--input", type=Path, help="可选：从本地 CSV 读取股票列表并应用过滤")
    universe.add_argument("--output", type=Path, default=Path("configs/universe_a_share.csv"))
    universe.add_argument("--source", default="akshare", choices=["akshare"])
    universe.add_argument("--include-st", action="store_true")
    universe.add_argument("--include-bj", action="store_true")
    universe.add_argument("--exclude-star", action="store_true")
    universe.add_argument("--exclude-chinext", action="store_true")
    universe.add_argument("--min-list-days", type=int)

    review = subparsers.add_parser("review", help="复盘和验证工具")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    selections = review_sub.add_parser("selections", help="验证历史选股的未来收益")
    selections.add_argument("--tracker", type=Path, default=Path("data/review/selections.jsonl"))
    selections.add_argument("--csv", type=Path, required=True, help="包含后续行情的 OHLCV CSV")
    selections.add_argument("--horizons", default="1,3,5", help="验证周期，例如 1,3,5")

    trade_add = review_sub.add_parser("trade-add", help="记录一笔实际交易")
    trade_add.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
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
    trade_add.add_argument("--tags", default="", help="逗号分隔标签，例如 追高,计划内")
    trade_add.add_argument("--mistake-type", default="")
    trade_add.add_argument("--review", default="")

    trade_list = review_sub.add_parser("trade-list", help="列出交易日志")
    trade_list.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))

    trade_stats = review_sub.add_parser("trade-stats", help="统计交易日志")
    trade_stats.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))

    market = subparsers.add_parser("market", help="市场环境工具")
    market_sub = market.add_subparsers(dest="market_command", required=True)
    temperature = market_sub.add_parser("temperature", help="计算市场温度计")
    add_dataset_args(temperature)
    temperature.add_argument("--strategy", default="strong_stock_screen")
    temperature.add_argument("--config", type=Path, help="YAML 条件树策略配置")
    temperature.add_argument("--settings", type=Path, help="系统设置 YAML，覆盖评分和仓位规则")
    add_sector_context_args(temperature)

    sectors = market_sub.add_parser("sectors", help="计算板块/行业强度")
    add_dataset_args(sectors)
    sectors.add_argument("--strategy", default="strong_stock_screen")
    sectors.add_argument("--config", type=Path, help="YAML 条件树策略配置")
    sectors.add_argument("--settings", type=Path, help="系统设置 YAML，覆盖评分和仓位规则")
    sectors.add_argument("--sector-column", help="板块字段名，默认自动检测 sector/industry/board")
    sectors.add_argument("--top", type=int, default=10)

    portfolio = subparsers.add_parser("portfolio", help="组合和仓位工具")
    portfolio_sub = portfolio.add_subparsers(dest="portfolio_command", required=True)
    allocate = portfolio_sub.add_parser("allocate", help="根据市场温度和候选评分生成仓位建议")
    add_dataset_args(allocate)
    allocate.add_argument("--strategy", default="strong_stock_screen")
    allocate.add_argument("--config", type=Path, help="YAML 条件树策略配置")
    allocate.add_argument("--settings", type=Path, help="系统设置 YAML，覆盖评分和仓位规则")
    allocate.add_argument("--cash", type=float, default=100000)
    allocate.add_argument("--top", type=int, default=5)
    add_sector_context_args(allocate)

    precheck = portfolio_sub.add_parser("precheck", help="交易前纪律检查")
    add_dataset_args(precheck)
    precheck.add_argument("--symbol", required=True)
    precheck.add_argument("--entry-price", type=float, required=True)
    precheck.add_argument("--planned-pct", type=float, required=True)
    precheck.add_argument("--stop-price", type=float)
    precheck.add_argument("--target-price", type=float)
    precheck.add_argument("--strategy", default="strong_stock_screen")
    precheck.add_argument("--config", type=Path, help="YAML 条件树策略配置")
    precheck.add_argument("--settings", type=Path, help="系统设置 YAML，覆盖评分和仓位规则")
    precheck.add_argument("--cash", type=float, default=100000)
    precheck.add_argument("--top", type=int, default=5)
    add_sector_context_args(precheck)

    positions = portfolio_sub.add_parser("positions", help="从交易日志重建当前持仓")
    positions.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    positions.add_argument("--cash", type=float, default=100000)
    positions.add_argument("--price", action="append", default=[], help="当前价，格式 symbol=price，可重复传入")

    holding_risk = portfolio_sub.add_parser("risk", help="检查当前持仓风险")
    holding_risk.add_argument("--journal", type=Path, default=Path("data/review/trades.jsonl"))
    holding_risk.add_argument("--cash", type=float, default=100000)
    holding_risk.add_argument("--price", action="append", default=[], help="当前价，格式 symbol=price，可重复传入")
    holding_risk.add_argument("--stop", action="append", default=[], help="止损价，格式 symbol=price，可重复传入")
    holding_risk.add_argument("--max-exposure-pct", type=float, default=0.8)
    holding_risk.add_argument("--max-position-pct", type=float, default=0.2)

    optimize = subparsers.add_parser("optimize", help="策略实验和参数优化工具")
    optimize_sub = optimize.add_subparsers(dest="optimize_command", required=True)
    experiments = optimize_sub.add_parser("experiments", help="批量运行策略参数实验")
    experiments.add_argument("--csv", type=Path, required=True, help="OHLCV CSV 文件路径")
    experiments.add_argument("--preset", default="strong_stock_basic", help="内置实验预设")
    experiments.add_argument("--cases", type=Path, help="YAML 参数实验配置")
    experiments.add_argument("--horizons", default="1,3,5", help="验证周期，例如 1,3,5")
    experiments.add_argument("--top", type=int, default=5)
    experiments.add_argument("--min-history", type=int, default=25)
    experiments.add_argument("--recommend-horizon", type=int, default=3, help="报告推荐优先参考的验证周期")
    experiments.add_argument("--recommend-min-count", type=int, default=5, help="报告给出推荐所需的最小样本数")
    experiments.add_argument("--output", type=Path, help="可选：保存 JSON 实验结果")
    experiments.add_argument("--report-output", type=Path, help="可选：保存 Markdown 实验报告")
    experiments.add_argument("--summary-output", type=Path, help="可选：保存结构化推荐摘要 JSON")

    return parser


def add_dataset_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--csv", type=Path, help="OHLCV CSV 文件路径")
    parser.add_argument("--cache-dir", type=Path, help="本地日线缓存目录")
    parser.add_argument("--universe", type=Path, help="股票池 CSV，用于从缓存加载多股票数据")


def add_sector_context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sector-column", help="板块字段名，默认自动检测 sector/industry/board")
    parser.add_argument("--sector-top", type=int, default=5, help="主线板块数量，用于加权和过滤")
    parser.add_argument("--only-top-sectors", action="store_true", help="只保留主线板块内的候选")


def add_dragon_gate_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--entry-gate",
        choices=["all", "pass-watch", "pass"],
        default="all",
        help="仅 dragon_leader 使用：按进场闸门过滤信号",
    )


def add_dragon_entry_model_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dragon-entry-model",
        choices=["signal-day", "next-open"],
        default="signal-day",
        help="仅 dragon_leader 使用：信号日买入或次日开盘买入模型",
    )
    parser.add_argument("--max-next-open-gap", type=float, default=0.07, help="next-open 买点允许的最高开盘涨幅")
    parser.add_argument("--min-next-open-gap", type=float, default=-0.03, help="next-open 买点允许的最低开盘涨幅")
    parser.add_argument("--allow-next-open-below-ma5", action="store_true", help="允许 next-open 买点低于 MA5")


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
    return load_settings(getattr(args, "settings", None))


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
    strategy = strategy_from_args(args)
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
        SelectionTracker(args.tracker).record_many(records_from_selection(strategy.name, rows))
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))


def run_dragon_screen(args: argparse.Namespace) -> None:
    args.strategy = "dragon_leader"
    args.config = None
    run_screen(args)


def run_dragon_check(args: argparse.Namespace) -> None:
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    diagnostics = latest_dragon_diagnostics(frame, args.symbol)
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str))


def run_backtest(args: argparse.Namespace) -> None:
    frame = read_ohlcv_csv(args.csv)
    strategy = strategy_from_args(args)
    engine = BacktestEngine(BacktestConfig(initial_cash=args.cash, buy_price_field=args.buy_price))
    result = engine.run(frame, strategy)
    print(json.dumps(result.summary(), ensure_ascii=False, indent=2))


def run_daily_report(args: argparse.Namespace) -> None:
    settings = settings_from_args(args)
    selected: list[dict] = []
    risks = ["尚未接入实盘交易；所有候选只能作为研究和复盘输入。"]
    market_view = "等待接入盘后行情、指数环境和新闻数据。"
    market_temperature = None
    allocation_plan = None

    if args.csv or (args.cache_dir and args.universe):
        frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
        strategy = strategy_from_args(args)
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
        ).to_dict()
        SelectionTracker(args.tracker).record_many(records_from_selection(strategy.name, selected))
        market_view = f"基于 {strategy.name} 策略完成候选筛选，共 {len(selected)} 只。"
        risks.append("当前日报只基于技术面数据，尚未合并涨跌停、停牌、新闻和板块强度。")

    content = DailyReport().render(
        DailyReportInput(
            title="A股量化日报",
            market_view=market_view,
            selected=selected,
            risks=risks,
            market_temperature=market_temperature,
            allocation_plan=allocation_plan,
        )
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
        candidates = strategy.screen(frame)
        if not candidates.empty:
            from quant_system.screening.scoring import score_candidates

            candidates = score_candidates(candidates, settings.scoring.weights)
        market_temperature = calculate_market_temperature(frame, candidates).to_dict()
        horizons = tuple(int(item.strip()) for item in args.horizons.split(",") if item.strip())
        validation = validate_selection_file(args.tracker, args.csv, horizons=horizons)
        selection_summary = summarize_forward_returns(validation).to_dict(orient="records")
        gate_summary = summarize_forward_returns_by(validation, "entry_gate").to_dict(orient="records")

    trade_stats = summarize_trade_journal(TradeJournal(args.journal).list())
    experiment_summary = None
    if args.experiment_summary and args.experiment_summary.exists():
        experiment_summary = json.loads(args.experiment_summary.read_text(encoding="utf-8"))
    content = WeeklyReport().render(
        WeeklyReportInput(
            title="A股量化周报",
            market_temperature=market_temperature,
            selection_summary=selection_summary,
            gate_summary=gate_summary,
            trade_stats=trade_stats,
            experiment_summary=experiment_summary,
            notes=args.note,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(str(args.output))


def run_dragon_validation_report(args: argparse.Namespace) -> None:
    horizons = tuple(int(item.strip()) for item in args.horizons.split(",") if item.strip())
    validation = validate_selection_file(args.tracker, args.csv, horizons=horizons)
    signal_summary = summarize_forward_returns(validation).to_dict(orient="records")
    gate_summary = summarize_forward_returns_by(validation, "entry_gate").to_dict(orient="records")

    frame = read_ohlcv_csv(args.csv)
    strategy = create_strategy(
        "dragon_leader",
        entry_gate=args.entry_gate,
        entry_model=args.dragon_entry_model,
        max_next_open_gap=args.max_next_open_gap,
        min_next_open_gap=args.min_next_open_gap,
        require_next_open_above_ma5=not args.allow_next_open_below_ma5,
    )
    backtest_result = BacktestEngine(
        BacktestConfig(initial_cash=args.cash, buy_price_field=args.buy_price)
    ).run(frame, strategy)
    content = DragonValidationReport().render(
        DragonValidationInput(
            title="龙头战法双轨验证报告",
            entry_gate=args.entry_gate,
            entry_model=args.dragon_entry_model,
            buy_price=args.buy_price,
            signal_summary=signal_summary,
            gate_summary=gate_summary,
            backtest_summary=backtest_result.summary(),
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(str(args.output))


def run_briefing_report(args: argparse.Namespace) -> None:
    settings = settings_from_args(args)
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
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
    ).to_dict()
    prices = parse_price_overrides(args.price)
    stops = parse_price_overrides(args.stop)
    position_book = build_position_book(TradeJournal(args.journal).list(), cash=args.cash, prices=prices).to_dict()
    holding_risk = check_holding_risk(
        build_position_book(TradeJournal(args.journal).list(), cash=args.cash, prices=prices),
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
    content = BriefingReport().render(
        BriefingInput(
            title="A股量化作战简报",
            market_temperature=market_temperature,
            candidates=candidates.to_dict(orient="records"),
            allocation_plan=allocation_plan,
            position_book=position_book,
            holding_risk=holding_risk,
            sectors=sectors,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(str(args.output))


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
    stocks = read_universe(args.universe)
    if args.limit:
        stocks = stocks[: args.limit]

    manifest = CacheManifest(args.manifest)
    summary = {"ok": 0, "failed": 0, "items": []}
    for stock in stocks:
        try:
            if not args.refresh:
                try:
                    cached = load_daily_cache(args.cache_dir, stock.symbol)
                except FileNotFoundError:
                    cached = None
                if cached is not None:
                    entry = CacheManifestEntry(
                        symbol=stock.symbol,
                        provider="cache",
                        path=str(args.cache_dir / stock.symbol),
                        start=args.start,
                        end=args.end,
                        rows=len(cached),
                        status="skipped",
                    )
                    summary["ok"] += 1
                    manifest.append(entry)
                    summary["items"].append(entry.__dict__)
                    continue
            result = fetch_with_fallback(
                symbol=stock.symbol,
                start=args.start,
                end=args.end,
                adjust=args.adjust,
                source=args.source,
            )
            path = save_daily_cache(args.cache_dir, stock.symbol, result.frame)
            entry = CacheManifestEntry(
                symbol=stock.symbol,
                provider=result.provider,
                path=str(path),
                start=args.start,
                end=args.end,
                rows=len(result.frame),
                status="ok",
            )
            summary["ok"] += 1
        except Exception as exc:  # noqa: BLE001 - batch update should continue.
            entry = CacheManifestEntry(
                symbol=stock.symbol,
                provider=args.source,
                path="",
                start=args.start,
                end=args.end,
                rows=0,
                status="failed",
                error=str(exc),
            )
            summary["failed"] += 1
        manifest.append(entry)
        summary["items"].append(entry.__dict__)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


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


def run_data_universe(args: argparse.Namespace) -> None:
    try:
        status = "ok"
        fallback_error = ""
        if args.input:
            raw = pd.read_csv(args.input, dtype={"symbol": str, "code": str})
        else:
            if args.source != "akshare":
                raise ValueError(f"Unsupported universe source: {args.source}")
            try:
                raw = fetch_akshare_universe()
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


def run_review_selections(args: argparse.Namespace) -> None:
    horizons = tuple(int(item.strip()) for item in args.horizons.split(",") if item.strip())
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
    )
    TradeJournal(args.journal).add(entry)
    print(json.dumps(entry.to_record(), ensure_ascii=False, indent=2))


def run_review_trade_list(args: argparse.Namespace) -> None:
    records = TradeJournal(args.journal).list()
    print(json.dumps(records, ensure_ascii=False, indent=2, default=str))


def run_review_trade_stats(args: argparse.Namespace) -> None:
    records = TradeJournal(args.journal).list()
    print(json.dumps(summarize_trade_journal(records), ensure_ascii=False, indent=2))


def run_market_temperature(args: argparse.Namespace) -> None:
    settings = settings_from_args(args)
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
    candidates = strategy.screen(frame)
    candidates = enrich_and_score_candidates(
        frame,
        candidates,
        settings.scoring.weights,
        sector_column=args.sector_column,
        sector_top=args.top,
        only_top_sectors=False,
    )
    temperature = calculate_market_temperature(frame, candidates)
    print(json.dumps(temperature.to_dict(), ensure_ascii=False, indent=2))


def run_market_sectors(args: argparse.Namespace) -> None:
    settings = settings_from_args(args)
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
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
    settings = settings_from_args(args)
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
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
    )
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))


def run_portfolio_precheck(args: argparse.Namespace) -> None:
    settings = settings_from_args(args)
    frame = load_ohlcv_dataset(args.csv, args.cache_dir, args.universe)
    strategy = strategy_from_args(args)
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
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


def run_portfolio_positions(args: argparse.Namespace) -> None:
    prices = parse_price_overrides(args.price)
    records = TradeJournal(args.journal).list()
    book = build_position_book(records, cash=args.cash, prices=prices)
    print(json.dumps(book.to_dict(), ensure_ascii=False, indent=2))


def run_portfolio_risk(args: argparse.Namespace) -> None:
    prices = parse_price_overrides(args.price)
    stops = parse_price_overrides(args.stop)
    records = TradeJournal(args.journal).list()
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
    elif args.command == "report":
        if args.report_command == "daily":
            run_daily_report(args)
        elif args.report_command == "weekly":
            run_weekly_report(args)
        elif args.report_command == "briefing":
            run_briefing_report(args)
        elif args.report_command == "dragon":
            run_dragon_validation_report(args)
    elif args.command == "data":
        if args.data_command == "fetch-daily":
            run_data_fetch_daily(args)
        elif args.data_command == "fetch-batch":
            run_data_fetch_batch(args)
        elif args.data_command == "health":
            run_data_health(args)
        elif args.data_command == "universe":
            run_data_universe(args)
    elif args.command == "review":
        if args.review_command == "selections":
            run_review_selections(args)
        elif args.review_command == "trade-add":
            run_review_trade_add(args)
        elif args.review_command == "trade-list":
            run_review_trade_list(args)
        elif args.review_command == "trade-stats":
            run_review_trade_stats(args)
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
    else:
        parser.error(f"Unknown command: {args.command}")
