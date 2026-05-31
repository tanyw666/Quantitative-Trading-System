from pathlib import Path

import pandas as pd

from quant_system.storage.sqlite_store import SQLiteStore


def test_sqlite_store_round_trip(tmp_path: Path):
    store = SQLiteStore(tmp_path / "quant.sqlite")
    store.init()

    universe = pd.DataFrame(
        {
            "symbol": ["000001"],
            "name": ["平安银行"],
            "market": ["SZ"],
            "board": ["MAIN"],
            "industry": ["Bank"],
            "sector": ["Financials"],
            "listing_date": ["1991-04-03"],
            "is_st": [0],
        }
    )
    bars = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "symbol": ["000001", "000001"],
            "open": [10, 11],
            "high": [11, 12],
            "low": [9, 10],
            "close": [10.5, 11.5],
            "volume": [1000, 1200],
            "amount": [None, None],
            "turnover": [None, None],
        }
    )

    assert store.upsert_universe(universe) == 1
    assert store.upsert_daily_bars(bars, source="akshare", adjust="qfq") == 2

    universe_read = store.read_universe()
    bars_read = store.read_daily_bars(symbol="000001")

    assert universe_read["name"].tolist() == ["平安银行"]
    assert bars_read["close"].tolist() == [10.5, 11.5]


def test_sqlite_store_persists_selections_and_promotions(tmp_path: Path):
    store = SQLiteStore(tmp_path / "quant.sqlite")
    store.init()

    selections = [
        {
            "date": "2026-05-29",
            "strategy": "dragon_leader",
            "symbol": "1",
            "name": "Demo",
            "close": 10.5,
            "reason": "测试入选",
            "entry_gate": "pass",
            "dragon_state": "repair",
            "dragon_tags": "weak-to-strong",
            "dragon_score": 88,
            "seal_quality_score": 77,
        }
    ]
    promotion = {
        "created_at": "2026-05-29T09:00:00+00:00",
        "summary": "reports/summary.json",
        "output": "configs/strategies/promoted.yaml",
        "ok": True,
        "backtest_requested": True,
        "buy_price_field": "open",
        "cash": 100000,
        "validation": {"ok": True},
        "backtest": {"total_return": 0.05, "sharpe": 1.2, "trades": 3},
    }

    assert store.insert_selections(selections) == 1
    promotion_id = store.insert_strategy_promotion(promotion)

    selected = store.read_selections(strategy="dragon_leader")
    promotions = store.read_strategy_promotions(limit=1)

    assert promotion_id == 1
    assert selected.loc[0, "symbol"] == "000001"
    assert selected.loc[0, "entry_gate"] == "pass"
    assert promotions.loc[0, "output_path"] == "configs/strategies/promoted.yaml"
    assert promotions.loc[0, "total_return"] == 0.05


def test_sqlite_store_persists_trades(tmp_path: Path):
    store = SQLiteStore(tmp_path / "quant.sqlite")
    store.init()

    trade_id = store.insert_trade(
        {
            "date": "2026-05-29",
            "symbol": "1",
            "side": "buy",
            "price": 10.5,
            "quantity": 100,
            "reason": "breakout",
            "name": "Demo",
            "strategy": "dragon",
            "market_regime": "hot",
            "planned_pct": 0.1,
            "actual_pct": 0.08,
            "planned_price": 10.0,
            "stop_price": 9.5,
            "target_price": 12.0,
            "amount": 1050.0,
            "execution_deviation_pct": 0.05,
            "tags": ["plan", "breakout"],
            "mistake_type": "",
            "review": "ok",
            "gate_status": "warn",
            "gate_message": "只允许计划内确认单",
            "gate_reasons": ["交易前预检存在预警项"],
            "workflow_summary": "reports/premarket_workflow.json",
            "discipline_exception": True,
            "exception_reason": "approved exception",
            "order_approval_path": "reports/approval.json",
            "order_approval_created_at": "2026-05-29T09:35:00+00:00",
            "order_approval_status": "pass",
            "order_approval_decision": "PASS",
            "approved_pct": 0.08,
            "approved_value": 8000,
            "approved_quantity": 700,
        }
    )

    trades = store.read_trades(symbol="000001")

    assert trade_id == 1
    assert trades.loc[0, "symbol"] == "000001"
    assert trades.loc[0, "side"] == "BUY"
    assert trades.loc[0, "amount"] == 1050.0
    assert '"breakout"' in trades.loc[0, "tags_json"]
    assert trades.loc[0, "gate_status"] == "warn"
    assert "交易前预检存在预警项" in trades.loc[0, "gate_reasons_json"]
    assert trades.loc[0, "discipline_exception"] == 1
    assert trades.loc[0, "exception_reason"] == "approved exception"
    assert trades.loc[0, "order_approval_status"] == "pass"
    assert trades.loc[0, "approved_quantity"] == 700


def test_sqlite_store_persists_strategy_constraints(tmp_path: Path):
    store = SQLiteStore(tmp_path / "quant.sqlite")
    store.init()

    row_id = store.insert_strategy_constraint(
        {
            "created_at": "2026-05-29T09:30:00+00:00",
            "source": "portfolio.precheck",
            "strategy": "dragon",
            "symbol": "000001",
            "alert_level": "warn",
            "action": "keep",
            "alerts": ["execution_deviation"],
            "note": "demo note",
        }
    )

    records = store.read_strategy_constraints(limit=1)

    assert row_id == 1
    assert records.loc[0, "strategy"] == "dragon"
    assert records.loc[0, "source"] == "portfolio.precheck"
    assert "execution_deviation" in records.loc[0, "alerts_json"]


def test_sqlite_store_persists_discipline_records(tmp_path: Path):
    store = SQLiteStore(tmp_path / "quant.sqlite")
    store.init()

    row_id = store.insert_discipline_record(
        {
            "created_at": "2026-05-29T09:30:00+00:00",
            "date": "2026-05-29",
            "source": "report.daily",
            "status": "warn",
            "advice": ["Review gate violation"],
            "gate_violation_count": 1,
            "missing_gate_count": 0,
            "avg_execution_deviation_pct": 0.03,
            "holding_status": "pass",
            "target_exposure_pct": 0.3,
            "allocated_pct": 0.4,
        }
    )

    records = store.read_discipline_records(limit=1)

    assert row_id == 1
    assert records.loc[0, "source"] == "report.daily"
    assert records.loc[0, "status"] == "warn"
    assert "Review gate violation" in records.loc[0, "advice_json"]


def test_sqlite_store_persists_plan_lifecycle_records(tmp_path: Path):
    store = SQLiteStore(tmp_path / "quant.sqlite")
    store.init()

    trade_plan_id = store.insert_trade_plan(
        {
            "created_at": "2026-05-29T09:00:00+00:00",
            "trade_date": "2026-05-29",
            "symbol": "1",
            "name": "Demo",
            "strategy": "dragon",
            "market_regime": "warm",
            "stance": "watch",
            "status": "pass",
            "gate_status": "pass",
            "planned_pct": 0.08,
            "planned_value": 8000,
            "allowed_pct": 0.08,
            "allowed_value": 8000,
            "entry_price": 10,
            "stop_price": 9.5,
            "target_price": 12,
        }
    )
    action_id = store.insert_position_action_plan(
        {
            "created_at": "2026-05-29T10:00:00+00:00",
            "action_date": "2026-05-29",
            "status": "warn",
            "total_actions": 1,
            "exit_count": 1,
            "actions": [{"symbol": "000001", "action": "exit", "sell_quantity": 100}],
        }
    )
    exit_id = store.insert_exit_plan(
        {
            "created_at": "2026-05-29T11:00:00+00:00",
            "plan_date": "2026-05-29",
            "status": "block",
            "total_positions": 1,
            "sell_all_count": 1,
            "total_sell_quantity": 100,
            "expected_cash_release": 1000,
            "items": [{"symbol": "000001", "action": "sell_all", "sell_quantity": 100}],
        }
    )
    lifecycle_id = store.insert_lifecycle_snapshot(
        {
            "created_at": "2026-05-29T12:00:00+00:00",
            "snapshot_date": "2026-05-29",
            "status": "block",
            "trade_plan": {"records": 1},
            "lots": {"open_lots": 1, "stale_open_lots": 0},
            "holding_actions": {"exit_count": 1, "reduce_count": 0},
            "exit_plan": {"sell_all_count": 1, "take_profit_count": 0},
            "execution": {"trade_plan_match_rate": 1.0, "exit_execution_rate": 0.0},
        },
        snapshot_date="2026-05-29",
    )

    assert trade_plan_id == 1
    assert action_id == 1
    assert exit_id == 1
    assert lifecycle_id == 1
    assert store.read_trade_plans().loc[0, "symbol"] == "000001"
    assert store.read_position_action_plans().loc[0, "exit_count"] == 1
    assert store.read_exit_plans().loc[0, "status"] == "block"
    assert store.read_lifecycle_snapshots().loc[0, "trade_plan_match_rate"] == 1.0


def test_sqlite_store_persists_trading_day_states(tmp_path: Path):
    store = SQLiteStore(tmp_path / "quant.sqlite")
    store.init()

    row_id = store.insert_trading_day_state(
        {
            "created_at": "2026-05-30T15:30:00+08:00",
            "date": "2026-05-30",
            "source": "workflow.trading-day",
            "status": "warn",
            "phase_count": 4,
            "pass_count": 3,
            "warn_count": 1,
            "block_count": 0,
            "action_item_count": 2,
            "phases": [{"phase": "intraday", "status": "warn"}],
            "action_items": ["检查确认单"],
        }
    )

    records = store.read_trading_day_states(limit=1)

    assert row_id == 1
    assert records.loc[0, "state_date"] == "2026-05-30"
    assert records.loc[0, "status"] == "warn"
    assert '"workflow.trading-day"' in records.loc[0, "payload_json"]


def test_sqlite_store_persists_order_approvals(tmp_path: Path):
    store = SQLiteStore(tmp_path / "quant.sqlite")
    store.init()

    row_id = store.insert_order_approval(
        {
            "created_at": "2026-05-30T10:00:00+08:00",
            "symbol": "1",
            "status": "warn",
            "decision": "WARN: only continue with reduced size after manual acceptance.",
            "confirmed_pct": 0.05,
            "confirmed_value": 5000,
            "suggested_quantity": 500,
            "evidence": {"pretrade_status": "pass", "tradability_status": "warn"},
            "reasons": ["tradability.price_vs_close: elevated chase risk"],
            "action_items": ["Reduce size before order entry."],
        }
    )

    records = store.read_order_approvals(symbol="000001", limit=1)

    assert row_id == 1
    assert records.loc[0, "symbol"] == "000001"
    assert records.loc[0, "status"] == "warn"
    assert "pretrade_status" in records.loc[0, "evidence_json"]


def test_sqlite_store_persists_execution_confirmations(tmp_path: Path):
    store = SQLiteStore(tmp_path / "quant.sqlite")
    store.init()

    row_id = store.insert_execution_confirmation(
        {
            "created_at": "2026-05-30T09:35:00+08:00",
            "symbol": "1",
            "status": "warn",
            "decision": "WARN",
            "current_price": 10.2,
            "reference_price": 10.0,
            "price_deviation_pct": 0.02,
            "requested_pct": 0.1,
            "confirmed_pct": 0.05,
            "requested_value": 10000,
            "confirmed_value": 5000,
            "suggested_quantity": 400,
            "lot_size": 100,
            "final_gate_status": "pass",
            "pretrade_status": "warn",
            "checks": [{"name": "price_drift", "status": "warn", "message": "small chase"}],
            "action_items": ["Reduce size before order entry."],
        }
    )

    records = store.read_execution_confirmations(symbol="000001", limit=1)

    assert row_id == 1
    assert records.loc[0, "symbol"] == "000001"
    assert records.loc[0, "status"] == "warn"
    assert records.loc[0, "suggested_quantity"] == 400
    assert "price_drift" in records.loc[0, "checks_json"]
