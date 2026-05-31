from quant_system.portfolio.execution_audit import summarize_execution_audit


def test_execution_audit_detects_block_violation_and_missing_writeback():
    confirms = [
        {
            "created_at": "2026-05-30T09:30:00+00:00",
            "symbol": "000001",
            "status": "block",
            "current_price": 10.0,
            "confirmed_value": 0.0,
            "suggested_quantity": 0,
        },
        {
            "created_at": "2026-05-30T09:35:00+00:00",
            "symbol": "000002",
            "status": "pass",
            "current_price": 20.0,
            "confirmed_value": 10000.0,
            "suggested_quantity": 500,
        },
    ]
    trades = [
        {
            "date": "2026-05-30",
            "symbol": "000001",
            "side": "BUY",
            "price": 10.2,
            "quantity": 100,
            "amount": 1020.0,
            "execution_confirmation_created_at": "2026-05-30T09:30:00+00:00",
            "review": "",
        }
    ]

    summary = summarize_execution_audit(confirms, trades, lookahead_days=1, limit=10)

    assert summary["total_confirms"] == 2
    assert summary["matched_trade_count"] == 1
    assert summary["missing_trade_writeback_count"] == 1
    assert summary["block_count"] >= 1
    assert any("confirmation status was block" in " ".join(record["reasons"]).lower() for record in summary["records"])


def test_execution_audit_detects_trade_without_confirmation():
    summary = summarize_execution_audit(
        [],
        [
            {
                "date": "2026-05-30",
                "symbol": "000003",
                "side": "BUY",
                "price": 12.0,
                "quantity": 100,
                "amount": 1200.0,
                "planned_price": 11.8,
                "gate_status": "pass",
            }
        ],
        limit=10,
    )

    assert summary["missing_confirmation_trade_count"] == 1
    assert summary["records"][0]["audit_type"] == "orphan_trade"
    assert summary["records"][0]["status"] == "block"
