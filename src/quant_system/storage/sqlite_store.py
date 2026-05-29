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
    source TEXT NOT NULL DEFAULT '',
    adjust TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (symbol, date)
);

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
        data["is_st"] = data.get("is_st", False).astype(int)
        data["listing_date"] = data["listing_date"].fillna("").astype(str)
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
        data["amount"] = data["amount"] if "amount" in data.columns else None
        data["turnover"] = data["turnover"] if "turnover" in data.columns else None
        data["source"] = source
        data["adjust"] = adjust
        rows = data.to_dict(orient="records")
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            conn.executemany(
                """
                INSERT INTO daily_bars
                (symbol, date, open, high, low, close, volume, amount, turnover, source, adjust)
                VALUES
                (:symbol, :date, :open, :high, :low, :close, :volume, :amount, :turnover, :source, :adjust)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    amount=excluded.amount,
                    turnover=excluded.turnover,
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
                 gate_reasons_json, workflow_summary, discipline_exception, exception_reason, payload_json)
                VALUES
                (:trade_date, :symbol, :side, :price, :quantity, :reason, :name, :strategy, :market_regime,
                 :planned_pct, :actual_pct, :planned_price, :stop_price, :target_price, :amount,
                 :execution_deviation_pct, :tags_json, :mistake_type, :review, :gate_status, :gate_message,
                 :gate_reasons_json, :workflow_summary, :discipline_exception, :exception_reason, :payload_json)
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
    }
    for column, statement in trade_migrations.items():
        if column not in trade_columns:
            conn.execute(statement)
    conn.commit()
