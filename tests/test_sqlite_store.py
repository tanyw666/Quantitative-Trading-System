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
