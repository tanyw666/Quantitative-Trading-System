from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import json


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS universe (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT NOT NULL DEFAULT 'A',
    board TEXT NOT NULL DEFAULT '',
    industry TEXT NOT NULL DEFAULT '',
    sector TEXT NOT NULL DEFAULT '',
    listing_date TEXT NOT NULL DEFAULT '',
    is_st INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_bars (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    amount REAL,
    turnover REAL,
    pre_close REAL,
    pct_change REAL,
    turnover_rate REAL,
    source TEXT NOT NULL DEFAULT '',
    adjust TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_bars_date ON daily_bars(date);

CREATE TABLE IF NOT EXISTS adjustment_factors (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    adjust_factor REAL NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_adjustment_factors_date ON adjustment_factors(date);

CREATE TABLE IF NOT EXISTS minute_bar_catalog (
    symbol TEXT NOT NULL,
    period TEXT NOT NULL DEFAULT '1',
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    adjust TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL,
    rows INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, period, start, end, adjust)
);

CREATE INDEX IF NOT EXISTS idx_minute_bar_catalog_symbol ON minute_bar_catalog(symbol, period, fetched_at);

CREATE TABLE IF NOT EXISTS fetch_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    rows INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS selections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    selected_at TEXT NOT NULL,
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    close REAL,
    reason TEXT NOT NULL DEFAULT '',
    entry_gate TEXT NOT NULL DEFAULT '',
    dragon_state TEXT NOT NULL DEFAULT '',
    dragon_tags TEXT NOT NULL DEFAULT '',
    dragon_score REAL NOT NULL DEFAULT 0,
    seal_quality_score REAL NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_selections_strategy_date ON selections(strategy, selected_at);
CREATE INDEX IF NOT EXISTS idx_selections_symbol_date ON selections(symbol, selected_at);

CREATE TABLE IF NOT EXISTS strategy_promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    summary_path TEXT NOT NULL DEFAULT '',
    output_path TEXT NOT NULL DEFAULT '',
    strategy_name TEXT NOT NULL DEFAULT '',
    ok INTEGER NOT NULL DEFAULT 0,
    backtest_requested INTEGER NOT NULL DEFAULT 0,
    buy_price_field TEXT NOT NULL DEFAULT '',
    cash REAL NOT NULL DEFAULT 0,
    total_return REAL,
    sharpe REAL,
    trades INTEGER,
    validation_json TEXT NOT NULL DEFAULT '{}',
    backtest_json TEXT NOT NULL DEFAULT '{}',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_strategy_promotions_created_at ON strategy_promotions(created_at);
CREATE INDEX IF NOT EXISTS idx_strategy_promotions_output_path ON strategy_promotions(output_path);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    strategy TEXT NOT NULL DEFAULT '',
    market_regime TEXT NOT NULL DEFAULT '',
    planned_pct REAL NOT NULL DEFAULT 0,
    actual_pct REAL NOT NULL DEFAULT 0,
    planned_price REAL,
    stop_price REAL,
    target_price REAL,
    amount REAL NOT NULL DEFAULT 0,
    execution_deviation_pct REAL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    mistake_type TEXT NOT NULL DEFAULT '',
    review TEXT NOT NULL DEFAULT '',
    gate_status TEXT NOT NULL DEFAULT '',
    gate_message TEXT NOT NULL DEFAULT '',
    gate_reasons_json TEXT NOT NULL DEFAULT '[]',
    workflow_summary TEXT NOT NULL DEFAULT '',
    discipline_exception INTEGER NOT NULL DEFAULT 0,
    exception_reason TEXT NOT NULL DEFAULT '',
    order_approval_path TEXT NOT NULL DEFAULT '',
    order_approval_created_at TEXT NOT NULL DEFAULT '',
    order_approval_status TEXT NOT NULL DEFAULT '',
    order_approval_decision TEXT NOT NULL DEFAULT '',
    approved_pct REAL NOT NULL DEFAULT 0,
    approved_value REAL NOT NULL DEFAULT 0,
    approved_quantity INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trades_trade_date ON trades(trade_date);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_date ON trades(symbol, trade_date);

CREATE TABLE IF NOT EXISTS strategy_constraints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    strategy TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL DEFAULT '',
    alert_level TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    alerts_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_strategy_constraints_created_at ON strategy_constraints(created_at);
CREATE INDEX IF NOT EXISTS idx_strategy_constraints_strategy ON strategy_constraints(strategy, created_at);

CREATE TABLE IF NOT EXISTS discipline_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    record_date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    advice_json TEXT NOT NULL DEFAULT '[]',
    gate_violation_count INTEGER NOT NULL DEFAULT 0,
    missing_gate_count INTEGER NOT NULL DEFAULT 0,
    avg_execution_deviation_pct REAL NOT NULL DEFAULT 0,
    holding_status TEXT NOT NULL DEFAULT '',
    target_exposure_pct REAL NOT NULL DEFAULT 0,
    allocated_pct REAL NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_discipline_records_date ON discipline_records(record_date, id);
CREATE INDEX IF NOT EXISTS idx_discipline_records_status ON discipline_records(status, record_date);

CREATE TABLE IF NOT EXISTS trade_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    strategy TEXT NOT NULL DEFAULT '',
    market_regime TEXT NOT NULL DEFAULT '',
    stance TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    gate_status TEXT NOT NULL DEFAULT '',
    gate_reason TEXT NOT NULL DEFAULT '',
    planned_pct REAL NOT NULL DEFAULT 0,
    planned_value REAL NOT NULL DEFAULT 0,
    allowed_pct REAL NOT NULL DEFAULT 0,
    allowed_value REAL NOT NULL DEFAULT 0,
    entry_price REAL NOT NULL DEFAULT 0,
    stop_price REAL,
    target_price REAL,
    stop_loss_pct REAL,
    reward_risk REAL,
    max_loss_value REAL,
    expected_reward_value REAL,
    risk_grade TEXT NOT NULL DEFAULT '',
    discipline_exception INTEGER NOT NULL DEFAULT 0,
    exception_reason TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_trade_plans_trade_date ON trade_plans(trade_date, id);
CREATE INDEX IF NOT EXISTS idx_trade_plans_strategy_date ON trade_plans(strategy, trade_date);
CREATE INDEX IF NOT EXISTS idx_trade_plans_symbol_date ON trade_plans(symbol, trade_date);

CREATE TABLE IF NOT EXISTS position_action_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    action_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    total_actions INTEGER NOT NULL DEFAULT 0,
    exit_count INTEGER NOT NULL DEFAULT 0,
    reduce_count INTEGER NOT NULL DEFAULT 0,
    watch_count INTEGER NOT NULL DEFAULT 0,
    hold_count INTEGER NOT NULL DEFAULT 0,
    action_items_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_position_action_plans_action_date ON position_action_plans(action_date, id);
CREATE INDEX IF NOT EXISTS idx_position_action_plans_status ON position_action_plans(status, action_date);

CREATE TABLE IF NOT EXISTS exit_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    plan_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    total_positions INTEGER NOT NULL DEFAULT 0,
    sell_all_count INTEGER NOT NULL DEFAULT 0,
    take_profit_count INTEGER NOT NULL DEFAULT 0,
    reduce_count INTEGER NOT NULL DEFAULT 0,
    time_stop_count INTEGER NOT NULL DEFAULT 0,
    invalidated_count INTEGER NOT NULL DEFAULT 0,
    watch_count INTEGER NOT NULL DEFAULT 0,
    hold_count INTEGER NOT NULL DEFAULT 0,
    total_sell_quantity INTEGER NOT NULL DEFAULT 0,
    expected_cash_release REAL NOT NULL DEFAULT 0,
    lot_level INTEGER NOT NULL DEFAULT 0,
    action_items_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_exit_plans_plan_date ON exit_plans(plan_date, id);
CREATE INDEX IF NOT EXISTS idx_exit_plans_status ON exit_plans(status, plan_date);
CREATE INDEX IF NOT EXISTS idx_exit_plans_lot_level ON exit_plans(lot_level, plan_date);

CREATE TABLE IF NOT EXISTS lifecycle_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    trade_plan_records INTEGER NOT NULL DEFAULT 0,
    open_lots INTEGER NOT NULL DEFAULT 0,
    stale_open_lots INTEGER NOT NULL DEFAULT 0,
    action_exit_count INTEGER NOT NULL DEFAULT 0,
    action_reduce_count INTEGER NOT NULL DEFAULT 0,
    exit_sell_all_count INTEGER NOT NULL DEFAULT 0,
    exit_take_profit_count INTEGER NOT NULL DEFAULT 0,
    trade_plan_match_rate REAL NOT NULL DEFAULT 0,
    action_execution_rate REAL NOT NULL DEFAULT 0,
    exit_execution_rate REAL NOT NULL DEFAULT 0,
    lot_exit_execution_rate REAL NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_snapshots_date ON lifecycle_snapshots(snapshot_date, id);
CREATE INDEX IF NOT EXISTS idx_lifecycle_snapshots_status ON lifecycle_snapshots(status, snapshot_date);

CREATE TABLE IF NOT EXISTS trading_day_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    state_date TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    phase_count INTEGER NOT NULL DEFAULT 0,
    pass_count INTEGER NOT NULL DEFAULT 0,
    warn_count INTEGER NOT NULL DEFAULT 0,
    block_count INTEGER NOT NULL DEFAULT 0,
    action_item_count INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_trading_day_states_date ON trading_day_states(state_date, id);
CREATE INDEX IF NOT EXISTS idx_trading_day_states_status ON trading_day_states(status, state_date);

CREATE TABLE IF NOT EXISTS order_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL DEFAULT '',
    confirmed_pct REAL NOT NULL DEFAULT 0,
    confirmed_value REAL NOT NULL DEFAULT 0,
    suggested_quantity INTEGER NOT NULL DEFAULT 0,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    reasons_json TEXT NOT NULL DEFAULT '[]',
    action_items_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_order_approvals_created_at ON order_approvals(created_at, id);
CREATE INDEX IF NOT EXISTS idx_order_approvals_symbol ON order_approvals(symbol, created_at);
CREATE INDEX IF NOT EXISTS idx_order_approvals_status ON order_approvals(status, created_at);

CREATE TABLE IF NOT EXISTS execution_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL DEFAULT '',
    current_price REAL NOT NULL DEFAULT 0,
    reference_price REAL,
    price_deviation_pct REAL,
    requested_pct REAL NOT NULL DEFAULT 0,
    confirmed_pct REAL NOT NULL DEFAULT 0,
    requested_value REAL NOT NULL DEFAULT 0,
    confirmed_value REAL NOT NULL DEFAULT 0,
    suggested_quantity INTEGER NOT NULL DEFAULT 0,
    lot_size INTEGER NOT NULL DEFAULT 100,
    final_gate_status TEXT NOT NULL DEFAULT '',
    pretrade_status TEXT NOT NULL DEFAULT '',
    checks_json TEXT NOT NULL DEFAULT '[]',
    action_items_json TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_execution_confirmations_created_at ON execution_confirmations(created_at, id);
CREATE INDEX IF NOT EXISTS idx_execution_confirmations_symbol ON execution_confirmations(symbol, created_at);
CREATE INDEX IF NOT EXISTS idx_execution_confirmations_status ON execution_confirmations(status, created_at);
"""


@dataclass(frozen=True)
class SQLiteStore:
    path: Path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        _ensure_schema_migrations(conn)
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_universe(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        data = frame.copy()
        for column in ("industry", "sector", "listing_date"):
            if column not in data.columns:
                data[column] = ""
            data[column] = data[column].fillna("").astype(str)
        if "is_st" not in data.columns:
            data["is_st"] = 0
        else:
            data["is_st"] = data["is_st"].fillna(False).astype(int)
        rows = data[["symbol", "name", "market", "board", "industry", "sector", "listing_date", "is_st"]].to_dict(orient="records")
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.executemany(
                """
                INSERT INTO universe (symbol, name, market, board, industry, sector, listing_date, is_st, updated_at)
                VALUES (:symbol, :name, :market, :board, :industry, :sector, :listing_date, :is_st, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol) DO UPDATE SET
                    name=excluded.name,
                    market=excluded.market,
                    board=excluded.board,
                    industry=excluded.industry,
                    sector=excluded.sector,
                    listing_date=excluded.listing_date,
                    is_st=excluded.is_st,
                    updated_at=CURRENT_TIMESTAMP
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def read_universe(self) -> pd.DataFrame:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query("SELECT * FROM universe ORDER BY symbol", conn)

    def upsert_daily_bars(self, frame: pd.DataFrame, source: str = "", adjust: str = "") -> int:
        if frame.empty:
            return 0
        data = frame.copy()
        data["date"] = pd.to_datetime(data["date"]).dt.strftime("%Y-%m-%d")
        data["symbol"] = data["symbol"].astype(str).str.zfill(6)
        for column in ("amount", "turnover", "pre_close", "pct_change", "turnover_rate"):
            if column not in data.columns:
                data[column] = None
        data["source"] = source
        data["adjust"] = adjust
        rows = data.to_dict(orient="records")
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.executemany(
                """
                INSERT INTO daily_bars
                (symbol, date, open, high, low, close, volume, amount, turnover, pre_close, pct_change, turnover_rate, source, adjust)
                VALUES
                (:symbol, :date, :open, :high, :low, :close, :volume, :amount, :turnover, :pre_close, :pct_change, :turnover_rate, :source, :adjust)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    amount=excluded.amount,
                    turnover=excluded.turnover,
                    pre_close=excluded.pre_close,
                    pct_change=excluded.pct_change,
                    turnover_rate=excluded.turnover_rate,
                    source=excluded.source,
                    adjust=excluded.adjust
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def read_daily_bars(self, symbol: str | None = None, start: str | None = None, end: str | None = None) -> pd.DataFrame:
        clauses = []
        params: list[str] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(str(symbol).zfill(6))
        if start:
            clauses.append("date >= ?")
            params.append(pd.to_datetime(start).strftime("%Y-%m-%d"))
        if end:
            clauses.append("date <= ?")
            params.append(pd.to_datetime(end).strftime("%Y-%m-%d"))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(f"SELECT * FROM daily_bars {where} ORDER BY symbol, date", conn, params=params)

    def daily_coverage(self) -> dict[str, dict[str, Any]]:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            rows = conn.execute(
                """
                SELECT symbol, COUNT(*) rows, MIN(date) start, MAX(date) end
                FROM daily_bars
                GROUP BY symbol
                """
            ).fetchall()
        return {
            str(row["symbol"]).zfill(6): {
                "rows": int(row["rows"] or 0),
                "start": row["start"] or "",
                "end": row["end"] or "",
            }
            for row in rows
        }

    def upsert_adjustment_factors(self, frame: pd.DataFrame, source: str = "") -> int:
        if frame.empty:
            return 0
        data = frame.copy()
        data["symbol"] = data["symbol"].astype(str).str.zfill(6)
        data["date"] = pd.to_datetime(data["date"]).dt.strftime("%Y-%m-%d")
        if "adjust_factor" not in data.columns:
            raise ValueError("adjustment factor frame must contain adjust_factor")
        data["source"] = source
        rows = data[["symbol", "date", "adjust_factor", "source"]].to_dict(orient="records")
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO adjustment_factors (symbol, date, adjust_factor, source)
                VALUES (:symbol, :date, :adjust_factor, :source)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    adjust_factor=excluded.adjust_factor,
                    source=excluded.source
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def upsert_minute_bar_catalog(self, record: dict[str, Any]) -> None:
        row = {
            "symbol": str(record.get("symbol", "")).zfill(6),
            "period": str(record.get("period", "1")),
            "start": str(record.get("start", "")),
            "end": str(record.get("end", "")),
            "adjust": str(record.get("adjust", "")),
            "path": str(record.get("path", "")),
            "rows": int(record.get("rows", 0) or 0),
            "source": str(record.get("source", "")),
            "status": str(record.get("status", "")),
            "error": str(record.get("error", "")),
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO minute_bar_catalog
                (symbol, period, start, end, adjust, path, rows, source, status, error, fetched_at)
                VALUES
                (:symbol, :period, :start, :end, :adjust, :path, :rows, :source, :status, :error, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol, period, start, end, adjust) DO UPDATE SET
                    path=excluded.path,
                    rows=excluded.rows,
                    source=excluded.source,
                    status=excluded.status,
                    error=excluded.error,
                    fetched_at=CURRENT_TIMESTAMP
                """,
                row,
            )
            conn.commit()

    def market_catalog(self) -> dict[str, Any]:
        with self.connect() as conn:
            daily = conn.execute(
                "SELECT COUNT(*) rows, COUNT(DISTINCT symbol) symbols, MIN(date) start, MAX(date) end FROM daily_bars"
            ).fetchone()
            universe = conn.execute("SELECT COUNT(*) rows FROM universe").fetchone()
            factors = conn.execute(
                "SELECT COUNT(*) rows, COUNT(DISTINCT symbol) symbols, MIN(date) start, MAX(date) end FROM adjustment_factors"
            ).fetchone()
            minute = conn.execute(
                """
                SELECT COUNT(*) jobs, COALESCE(SUM(rows), 0) rows, COUNT(DISTINCT symbol) symbols,
                       MIN(start) start, MAX(end) end
                FROM minute_bar_catalog
                WHERE status = 'ok'
                """
            ).fetchone()
            fetch_jobs = conn.execute(
                """
                SELECT
                    COUNT(*) total,
                    SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) ok,
                    SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) failed
                FROM fetch_jobs
                """
            ).fetchone()
        return {
            "universe": {"rows": int(universe["rows"] or 0)},
            "daily_bars": {
                "rows": int(daily["rows"] or 0),
                "symbols": int(daily["symbols"] or 0),
                "start": daily["start"] or "",
                "end": daily["end"] or "",
            },
            "adjustment_factors": {
                "rows": int(factors["rows"] or 0),
                "symbols": int(factors["symbols"] or 0),
                "start": factors["start"] or "",
                "end": factors["end"] or "",
            },
            "minute_bars": {
                "catalog_jobs": int(minute["jobs"] or 0),
                "rows": int(minute["rows"] or 0),
                "symbols": int(minute["symbols"] or 0),
                "start": minute["start"] or "",
                "end": minute["end"] or "",
            },
            "fetch_jobs": {
                "total": int(fetch_jobs["total"] or 0),
                "ok": int(fetch_jobs["ok"] or 0),
                "failed": int(fetch_jobs["failed"] or 0),
            },
        }

    def log_fetch_job(self, symbol: str, start: str, end: str, source: str, status: str, rows: int = 0, error: str = "") -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                """
                INSERT INTO fetch_jobs (symbol, start, end, source, status, rows, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(symbol).zfill(6), start, end, source, status, rows, error),
            )
            conn.commit()

    def insert_selections(self, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        rows = []
        for record in records:
            rows.append(
                {
                    "selected_at": str(record.get("date", "")),
                    "strategy": str(record.get("strategy", "")),
                    "symbol": str(record.get("symbol", "")).zfill(6),
                    "name": str(record.get("name", "")),
                    "close": _optional_float(record.get("close")),
                    "reason": str(record.get("reason", "")),
                    "entry_gate": str(record.get("entry_gate", "")),
                    "dragon_state": str(record.get("dragon_state", "")),
                    "dragon_tags": str(record.get("dragon_tags", "")),
                    "dragon_score": float(record.get("dragon_score", 0) or 0),
                    "seal_quality_score": float(record.get("seal_quality_score", 0) or 0),
                    "payload_json": json.dumps(record, ensure_ascii=False),
                }
            )
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.executemany(
                """
                INSERT INTO selections
                (selected_at, strategy, symbol, name, close, reason, entry_gate, dragon_state, dragon_tags,
                 dragon_score, seal_quality_score, payload_json)
                VALUES
                (:selected_at, :strategy, :symbol, :name, :close, :reason, :entry_gate, :dragon_state, :dragon_tags,
                 :dragon_score, :seal_quality_score, :payload_json)
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def read_selections(self, strategy: str | None = None, symbol: str | None = None, limit: int | None = None) -> pd.DataFrame:
        clauses = []
        params: list[Any] = []
        if strategy:
            clauses.append("strategy = ?")
            params.append(strategy)
        if symbol:
            clauses.append("symbol = ?")
            params.append(str(symbol).zfill(6))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM selections {where} ORDER BY selected_at DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_strategy_promotion(self, record: dict[str, Any]) -> int:
        backtest = record.get("backtest") or {}
        validation = record.get("validation") or {}
        row = {
            "created_at": str(record.get("created_at", "")),
            "summary_path": str(record.get("summary", "")),
            "output_path": str(record.get("output", "")),
            "strategy_name": str(record.get("strategy_name", "")),
            "ok": 1 if record.get("ok") else 0,
            "backtest_requested": 1 if record.get("backtest_requested") else 0,
            "buy_price_field": str(record.get("buy_price_field", "")),
            "cash": float(record.get("cash", 0) or 0),
            "total_return": _optional_float(backtest.get("total_return")),
            "sharpe": _optional_float(backtest.get("sharpe")),
            "trades": _optional_int(backtest.get("trades")),
            "validation_json": json.dumps(validation, ensure_ascii=False),
            "backtest_json": json.dumps(backtest, ensure_ascii=False),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO strategy_promotions
                (created_at, summary_path, output_path, strategy_name, ok, backtest_requested, buy_price_field, cash,
                 total_return, sharpe, trades, validation_json, backtest_json, payload_json)
                VALUES
                (:created_at, :summary_path, :output_path, :strategy_name, :ok, :backtest_requested, :buy_price_field, :cash,
                 :total_return, :sharpe, :trades, :validation_json, :backtest_json, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_strategy_promotions(self, limit: int | None = None) -> pd.DataFrame:
        params: list[Any] = []
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM strategy_promotions ORDER BY created_at DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_trade(self, record: dict[str, Any]) -> int:
        row = {
            "trade_date": str(record.get("date", "")),
            "symbol": str(record.get("symbol", "")).zfill(6),
            "side": str(record.get("side", "")).upper(),
            "price": float(record.get("price", 0) or 0),
            "quantity": int(record.get("quantity", 0) or 0),
            "reason": str(record.get("reason", "")),
            "name": str(record.get("name", "")),
            "strategy": str(record.get("strategy", "")),
            "market_regime": str(record.get("market_regime", "")),
            "planned_pct": float(record.get("planned_pct", 0) or 0),
            "actual_pct": float(record.get("actual_pct", 0) or 0),
            "planned_price": _optional_float(record.get("planned_price")),
            "stop_price": _optional_float(record.get("stop_price")),
            "target_price": _optional_float(record.get("target_price")),
            "amount": float(record.get("amount", 0) or 0),
            "execution_deviation_pct": _optional_float(record.get("execution_deviation_pct")),
            "tags_json": json.dumps(record.get("tags", []), ensure_ascii=False),
            "mistake_type": str(record.get("mistake_type", "")),
            "review": str(record.get("review", "")),
            "gate_status": str(record.get("gate_status", "")),
            "gate_message": str(record.get("gate_message", "")),
            "gate_reasons_json": json.dumps(record.get("gate_reasons", []), ensure_ascii=False),
            "workflow_summary": str(record.get("workflow_summary", "")),
            "discipline_exception": 1 if record.get("discipline_exception") else 0,
            "exception_reason": str(record.get("exception_reason", "")),
            "order_approval_path": str(record.get("order_approval_path", "")),
            "order_approval_created_at": str(record.get("order_approval_created_at", "")),
            "order_approval_status": str(record.get("order_approval_status", "")),
            "order_approval_decision": str(record.get("order_approval_decision", "")),
            "approved_pct": float(record.get("approved_pct", 0) or 0),
            "approved_value": float(record.get("approved_value", 0) or 0),
            "approved_quantity": int(record.get("approved_quantity", 0) or 0),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO trades
                (trade_date, symbol, side, price, quantity, reason, name, strategy, market_regime,
                 planned_pct, actual_pct, planned_price, stop_price, target_price, amount,
                 execution_deviation_pct, tags_json, mistake_type, review, gate_status, gate_message,
                 gate_reasons_json, workflow_summary, discipline_exception, exception_reason,
                 order_approval_path, order_approval_created_at, order_approval_status, order_approval_decision,
                 approved_pct, approved_value, approved_quantity, payload_json)
                VALUES
                (:trade_date, :symbol, :side, :price, :quantity, :reason, :name, :strategy, :market_regime,
                 :planned_pct, :actual_pct, :planned_price, :stop_price, :target_price, :amount,
                 :execution_deviation_pct, :tags_json, :mistake_type, :review, :gate_status, :gate_message,
                 :gate_reasons_json, :workflow_summary, :discipline_exception, :exception_reason,
                 :order_approval_path, :order_approval_created_at, :order_approval_status, :order_approval_decision,
                 :approved_pct, :approved_value, :approved_quantity, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_trades(self, symbol: str | None = None, limit: int | None = None) -> pd.DataFrame:
        clauses = []
        params: list[Any] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(str(symbol).zfill(6))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM trades {where} ORDER BY trade_date DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_strategy_constraint(self, record: dict[str, Any]) -> int:
        row = {
            "created_at": str(record.get("created_at", "")),
            "source": str(record.get("source", "")),
            "strategy": str(record.get("strategy", "")),
            "symbol": str(record.get("symbol", "")),
            "alert_level": str(record.get("alert_level", "")),
            "action": str(record.get("action", "")),
            "note": str(record.get("note", "")),
            "alerts_json": json.dumps(record.get("alerts", []), ensure_ascii=False),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO strategy_constraints
                (created_at, source, strategy, symbol, alert_level, action, note, alerts_json, payload_json)
                VALUES
                (:created_at, :source, :strategy, :symbol, :alert_level, :action, :note, :alerts_json, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_strategy_constraints(self, limit: int | None = None) -> pd.DataFrame:
        params: list[Any] = []
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM strategy_constraints ORDER BY created_at DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_discipline_record(self, record: dict[str, Any]) -> int:
        row = {
            "created_at": str(record.get("created_at", "")),
            "record_date": str(record.get("date", "")),
            "source": str(record.get("source", "")),
            "status": str(record.get("status", "")),
            "advice_json": json.dumps(record.get("advice", []), ensure_ascii=False),
            "gate_violation_count": int(record.get("gate_violation_count", 0) or 0),
            "missing_gate_count": int(record.get("missing_gate_count", 0) or 0),
            "avg_execution_deviation_pct": float(record.get("avg_execution_deviation_pct", 0) or 0),
            "holding_status": str(record.get("holding_status", "")),
            "target_exposure_pct": float(record.get("target_exposure_pct", 0) or 0),
            "allocated_pct": float(record.get("allocated_pct", 0) or 0),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO discipline_records
                (created_at, record_date, source, status, advice_json, gate_violation_count, missing_gate_count,
                 avg_execution_deviation_pct, holding_status, target_exposure_pct, allocated_pct, payload_json)
                VALUES
                (:created_at, :record_date, :source, :status, :advice_json, :gate_violation_count, :missing_gate_count,
                 :avg_execution_deviation_pct, :holding_status, :target_exposure_pct, :allocated_pct, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_discipline_records(self, limit: int | None = None) -> pd.DataFrame:
        params: list[Any] = []
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM discipline_records ORDER BY record_date DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_trade_plan(self, record: dict[str, Any]) -> int:
        row = {
            "created_at": str(record.get("created_at", "")),
            "trade_date": str(record.get("trade_date", record.get("date", ""))),
            "symbol": str(record.get("symbol", "")).zfill(6),
            "name": str(record.get("name", "")),
            "strategy": str(record.get("strategy", "")),
            "market_regime": str(record.get("market_regime", "")),
            "stance": str(record.get("stance", "")),
            "status": str(record.get("status", "")),
            "gate_status": str(record.get("gate_status", "")),
            "gate_reason": str(record.get("gate_reason", "")),
            "planned_pct": float(record.get("planned_pct", 0) or 0),
            "planned_value": float(record.get("planned_value", 0) or 0),
            "allowed_pct": float(record.get("allowed_pct", 0) or 0),
            "allowed_value": float(record.get("allowed_value", 0) or 0),
            "entry_price": float(record.get("entry_price", 0) or 0),
            "stop_price": _optional_float(record.get("stop_price")),
            "target_price": _optional_float(record.get("target_price")),
            "stop_loss_pct": _optional_float(record.get("stop_loss_pct")),
            "reward_risk": _optional_float(record.get("reward_risk")),
            "max_loss_value": _optional_float(record.get("max_loss_value")),
            "expected_reward_value": _optional_float(record.get("expected_reward_value")),
            "risk_grade": str(record.get("risk_grade", "")),
            "discipline_exception": 1 if record.get("discipline_exception") else 0,
            "exception_reason": str(record.get("exception_reason", "")),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO trade_plans
                (created_at, trade_date, symbol, name, strategy, market_regime, stance, status, gate_status, gate_reason,
                 planned_pct, planned_value, allowed_pct, allowed_value, entry_price, stop_price, target_price,
                 stop_loss_pct, reward_risk, max_loss_value, expected_reward_value, risk_grade,
                 discipline_exception, exception_reason, payload_json)
                VALUES
                (:created_at, :trade_date, :symbol, :name, :strategy, :market_regime, :stance, :status, :gate_status, :gate_reason,
                 :planned_pct, :planned_value, :allowed_pct, :allowed_value, :entry_price, :stop_price, :target_price,
                 :stop_loss_pct, :reward_risk, :max_loss_value, :expected_reward_value, :risk_grade,
                 :discipline_exception, :exception_reason, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_trade_plans(
        self,
        strategy: str | None = None,
        symbol: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        clauses = []
        params: list[Any] = []
        if strategy:
            clauses.append("strategy = ?")
            params.append(strategy)
        if symbol:
            clauses.append("symbol = ?")
            params.append(str(symbol).zfill(6))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM trade_plans {where} ORDER BY trade_date DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_position_action_plan(self, record: dict[str, Any]) -> int:
        row = {
            "created_at": str(record.get("created_at", "")),
            "action_date": str(record.get("action_date", record.get("date", ""))),
            "status": str(record.get("status", "")),
            "total_actions": int(record.get("total_actions", 0) or 0),
            "exit_count": int(record.get("exit_count", 0) or 0),
            "reduce_count": int(record.get("reduce_count", 0) or 0),
            "watch_count": int(record.get("watch_count", 0) or 0),
            "hold_count": int(record.get("hold_count", 0) or 0),
            "action_items_json": json.dumps(record.get("action_items", []), ensure_ascii=False),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO position_action_plans
                (created_at, action_date, status, total_actions, exit_count, reduce_count, watch_count,
                 hold_count, action_items_json, payload_json)
                VALUES
                (:created_at, :action_date, :status, :total_actions, :exit_count, :reduce_count, :watch_count,
                 :hold_count, :action_items_json, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_position_action_plans(self, limit: int | None = None) -> pd.DataFrame:
        params: list[Any] = []
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM position_action_plans ORDER BY action_date DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_exit_plan(self, record: dict[str, Any]) -> int:
        items = list(record.get("items", []) or [])
        row = {
            "created_at": str(record.get("created_at", "")),
            "plan_date": str(record.get("plan_date", record.get("date", ""))),
            "status": str(record.get("status", "")),
            "total_positions": int(record.get("total_positions", 0) or 0),
            "sell_all_count": int(record.get("sell_all_count", 0) or 0),
            "take_profit_count": int(record.get("take_profit_count", 0) or 0),
            "reduce_count": int(record.get("reduce_count", 0) or 0),
            "time_stop_count": int(record.get("time_stop_count", 0) or 0),
            "invalidated_count": int(record.get("invalidated_count", 0) or 0),
            "watch_count": int(record.get("watch_count", 0) or 0),
            "hold_count": int(record.get("hold_count", 0) or 0),
            "total_sell_quantity": int(record.get("total_sell_quantity", 0) or 0),
            "expected_cash_release": float(record.get("expected_cash_release", 0) or 0),
            "lot_level": 1 if any(str(item.get("lot_id", "") or "").strip() for item in items) else 0,
            "action_items_json": json.dumps(record.get("action_items", []), ensure_ascii=False),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO exit_plans
                (created_at, plan_date, status, total_positions, sell_all_count, take_profit_count, reduce_count,
                 time_stop_count, invalidated_count, watch_count, hold_count, total_sell_quantity,
                 expected_cash_release, lot_level, action_items_json, payload_json)
                VALUES
                (:created_at, :plan_date, :status, :total_positions, :sell_all_count, :take_profit_count, :reduce_count,
                 :time_stop_count, :invalidated_count, :watch_count, :hold_count, :total_sell_quantity,
                 :expected_cash_release, :lot_level, :action_items_json, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_exit_plans(self, limit: int | None = None, lot_level: bool | None = None) -> pd.DataFrame:
        clauses = []
        params: list[Any] = []
        if lot_level is not None:
            clauses.append("lot_level = ?")
            params.append(1 if lot_level else 0)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM exit_plans {where} ORDER BY plan_date DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_lifecycle_snapshot(self, record: dict[str, Any], *, snapshot_date: str = "") -> int:
        trade_plan = dict(record.get("trade_plan") or {})
        lots = dict(record.get("lots") or {})
        holding = dict(record.get("holding_actions") or {})
        exit_plan = dict(record.get("exit_plan") or {})
        execution = dict(record.get("execution") or {})
        row = {
            "created_at": str(record.get("created_at", "")),
            "snapshot_date": snapshot_date or str(record.get("snapshot_date", "")),
            "status": str(record.get("status", "")),
            "trade_plan_records": int(trade_plan.get("records", 0) or 0),
            "open_lots": int(lots.get("open_lots", 0) or 0),
            "stale_open_lots": int(lots.get("stale_open_lots", 0) or 0),
            "action_exit_count": int(holding.get("exit_count", 0) or 0),
            "action_reduce_count": int(holding.get("reduce_count", 0) or 0),
            "exit_sell_all_count": int(exit_plan.get("sell_all_count", 0) or 0),
            "exit_take_profit_count": int(exit_plan.get("take_profit_count", 0) or 0),
            "trade_plan_match_rate": float(execution.get("trade_plan_match_rate", 0) or 0),
            "action_execution_rate": float(execution.get("action_execution_rate", 0) or 0),
            "exit_execution_rate": float(execution.get("exit_execution_rate", 0) or 0),
            "lot_exit_execution_rate": float(execution.get("lot_exit_execution_rate", 0) or 0),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO lifecycle_snapshots
                (created_at, snapshot_date, status, trade_plan_records, open_lots, stale_open_lots,
                 action_exit_count, action_reduce_count, exit_sell_all_count, exit_take_profit_count,
                 trade_plan_match_rate, action_execution_rate, exit_execution_rate, lot_exit_execution_rate, payload_json)
                VALUES
                (:created_at, :snapshot_date, :status, :trade_plan_records, :open_lots, :stale_open_lots,
                 :action_exit_count, :action_reduce_count, :exit_sell_all_count, :exit_take_profit_count,
                 :trade_plan_match_rate, :action_execution_rate, :exit_execution_rate, :lot_exit_execution_rate, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_lifecycle_snapshots(self, limit: int | None = None) -> pd.DataFrame:
        params: list[Any] = []
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM lifecycle_snapshots ORDER BY snapshot_date DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_trading_day_state(self, record: dict[str, Any]) -> int:
        row = {
            "created_at": str(record.get("created_at", "")),
            "state_date": str(record.get("date", "")),
            "source": str(record.get("source", "")),
            "status": str(record.get("status", "")),
            "phase_count": int(record.get("phase_count", 0) or 0),
            "pass_count": int(record.get("pass_count", 0) or 0),
            "warn_count": int(record.get("warn_count", 0) or 0),
            "block_count": int(record.get("block_count", 0) or 0),
            "action_item_count": int(record.get("action_item_count", 0) or 0),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO trading_day_states
                (created_at, state_date, source, status, phase_count, pass_count, warn_count, block_count,
                 action_item_count, payload_json)
                VALUES
                (:created_at, :state_date, :source, :status, :phase_count, :pass_count, :warn_count, :block_count,
                 :action_item_count, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_trading_day_states(self, limit: int | None = None) -> pd.DataFrame:
        params: list[Any] = []
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM trading_day_states ORDER BY state_date DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_order_approval(self, record: dict[str, Any]) -> int:
        row = {
            "created_at": str(record.get("created_at", "")),
            "symbol": str(record.get("symbol", "")).zfill(6),
            "status": str(record.get("status", "")),
            "decision": str(record.get("decision", "")),
            "confirmed_pct": float(record.get("confirmed_pct", 0) or 0),
            "confirmed_value": float(record.get("confirmed_value", 0) or 0),
            "suggested_quantity": int(record.get("suggested_quantity", 0) or 0),
            "evidence_json": json.dumps(record.get("evidence", {}), ensure_ascii=False),
            "reasons_json": json.dumps(record.get("reasons", []), ensure_ascii=False),
            "action_items_json": json.dumps(record.get("action_items", []), ensure_ascii=False),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO order_approvals
                (created_at, symbol, status, decision, confirmed_pct, confirmed_value, suggested_quantity,
                 evidence_json, reasons_json, action_items_json, payload_json)
                VALUES
                (:created_at, :symbol, :status, :decision, :confirmed_pct, :confirmed_value, :suggested_quantity,
                 :evidence_json, :reasons_json, :action_items_json, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_order_approvals(
        self,
        symbol: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        clauses = []
        params: list[Any] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(str(symbol).zfill(6))
        if status:
            clauses.append("status = ?")
            params.append(str(status))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM order_approvals {where} ORDER BY created_at DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )

    def insert_execution_confirmation(self, record: dict[str, Any]) -> int:
        row = {
            "created_at": str(record.get("created_at", "")),
            "symbol": str(record.get("symbol", "")).zfill(6),
            "status": str(record.get("status", "")),
            "decision": str(record.get("decision", "")),
            "current_price": float(record.get("current_price", 0) or 0),
            "reference_price": _optional_float(record.get("reference_price")),
            "price_deviation_pct": _optional_float(record.get("price_deviation_pct")),
            "requested_pct": float(record.get("requested_pct", 0) or 0),
            "confirmed_pct": float(record.get("confirmed_pct", 0) or 0),
            "requested_value": float(record.get("requested_value", 0) or 0),
            "confirmed_value": float(record.get("confirmed_value", 0) or 0),
            "suggested_quantity": int(record.get("suggested_quantity", 0) or 0),
            "lot_size": int(record.get("lot_size", 100) or 100),
            "final_gate_status": str(record.get("final_gate_status", "")),
            "pretrade_status": str(record.get("pretrade_status", "")),
            "checks_json": json.dumps(record.get("checks", []), ensure_ascii=False),
            "action_items_json": json.dumps(record.get("action_items", []), ensure_ascii=False),
            "payload_json": json.dumps(record, ensure_ascii=False),
        }
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            cursor = conn.execute(
                """
                INSERT INTO execution_confirmations
                (created_at, symbol, status, decision, current_price, reference_price, price_deviation_pct,
                 requested_pct, confirmed_pct, requested_value, confirmed_value, suggested_quantity, lot_size,
                 final_gate_status, pretrade_status, checks_json, action_items_json, payload_json)
                VALUES
                (:created_at, :symbol, :status, :decision, :current_price, :reference_price, :price_deviation_pct,
                 :requested_pct, :confirmed_pct, :requested_value, :confirmed_value, :suggested_quantity, :lot_size,
                 :final_gate_status, :pretrade_status, :checks_json, :action_items_json, :payload_json)
                """,
                row,
            )
            conn.commit()
            return int(cursor.lastrowid)

    def read_execution_confirmations(
        self,
        symbol: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        clauses = []
        params: list[Any] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(str(symbol).zfill(6))
        if status:
            clauses.append("status = ?")
            params.append(str(status))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = "LIMIT ?" if limit else ""
        if limit:
            params.append(int(limit))
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            return pd.read_sql_query(
                f"SELECT * FROM execution_confirmations {where} ORDER BY created_at DESC, id DESC {limit_clause}",
                conn,
                params=params,
            )


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    promotion_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(strategy_promotions)").fetchall()
    }
    if "strategy_name" not in promotion_columns:
        conn.execute("ALTER TABLE strategy_promotions ADD COLUMN strategy_name TEXT NOT NULL DEFAULT ''")
        conn.commit()
    trade_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(trades)").fetchall()
    }
    trade_migrations = {
        "gate_status": "ALTER TABLE trades ADD COLUMN gate_status TEXT NOT NULL DEFAULT ''",
        "gate_message": "ALTER TABLE trades ADD COLUMN gate_message TEXT NOT NULL DEFAULT ''",
        "gate_reasons_json": "ALTER TABLE trades ADD COLUMN gate_reasons_json TEXT NOT NULL DEFAULT '[]'",
        "workflow_summary": "ALTER TABLE trades ADD COLUMN workflow_summary TEXT NOT NULL DEFAULT ''",
        "discipline_exception": "ALTER TABLE trades ADD COLUMN discipline_exception INTEGER NOT NULL DEFAULT 0",
        "exception_reason": "ALTER TABLE trades ADD COLUMN exception_reason TEXT NOT NULL DEFAULT ''",
        "order_approval_path": "ALTER TABLE trades ADD COLUMN order_approval_path TEXT NOT NULL DEFAULT ''",
        "order_approval_created_at": "ALTER TABLE trades ADD COLUMN order_approval_created_at TEXT NOT NULL DEFAULT ''",
        "order_approval_status": "ALTER TABLE trades ADD COLUMN order_approval_status TEXT NOT NULL DEFAULT ''",
        "order_approval_decision": "ALTER TABLE trades ADD COLUMN order_approval_decision TEXT NOT NULL DEFAULT ''",
        "approved_pct": "ALTER TABLE trades ADD COLUMN approved_pct REAL NOT NULL DEFAULT 0",
        "approved_value": "ALTER TABLE trades ADD COLUMN approved_value REAL NOT NULL DEFAULT 0",
        "approved_quantity": "ALTER TABLE trades ADD COLUMN approved_quantity INTEGER NOT NULL DEFAULT 0",
    }
    for column, statement in trade_migrations.items():
        if column not in trade_columns:
            conn.execute(statement)
    daily_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(daily_bars)").fetchall()
    }
    daily_migrations = {
        "pre_close": "ALTER TABLE daily_bars ADD COLUMN pre_close REAL",
        "pct_change": "ALTER TABLE daily_bars ADD COLUMN pct_change REAL",
        "turnover_rate": "ALTER TABLE daily_bars ADD COLUMN turnover_rate REAL",
    }
    for column, statement in daily_migrations.items():
        if column not in daily_columns:
            conn.execute(statement)
    conn.commit()
