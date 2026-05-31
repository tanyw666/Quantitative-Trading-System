from quant_system.portfolio.approval_execution import (
    render_approval_execution_markdown,
    summarize_approval_execution,
)


def test_approval_execution_detects_block_violation_and_missing_writeback():
    approvals = [
        {
            "created_at": "2026-05-30T09:30:00+00:00",
            "symbol": "000001",
            "status": "block",
            "confirmed_value": 0,
            "suggested_quantity": 0,
        },
        {
            "created_at": "2026-05-30T09:35:00+00:00",
            "symbol": "000002",
            "status": "pass",
            "confirmed_value": 10000,
            "suggested_quantity": 1000,
        },
    ]
    trades = [
        {
            "date": "2026-05-30",
            "symbol": "000001",
            "side": "BUY",
            "price": 10,
            "quantity": 100,
            "amount": 1000,
            "order_approval_created_at": "2026-05-30T09:30:00+00:00",
            "review": "",
        }
    ]

    summary = summarize_approval_execution(approvals, trades, lookahead_days=1, limit=10)

    assert summary["total_approvals"] == 2
    assert summary["matched_trade_count"] == 1
    assert summary["approved_not_executed_count"] == 1
    assert summary["block_approval_executed_count"] == 1
    assert summary["block_count"] >= 1
    assert any("Approval status was block" in " ".join(record["reasons"]) for record in summary["records"])


def test_approval_execution_detects_trade_without_approval():
    summary = summarize_approval_execution(
        [],
        [
            {
                "date": "2026-05-30",
                "symbol": "000003",
                "side": "BUY",
                "price": 12,
                "quantity": 100,
                "amount": 1200,
                "planned_price": 11.8,
            }
        ],
        limit=10,
    )

    assert summary["missing_approval_trade_count"] == 1
    assert summary["records"][0]["audit_type"] == "orphan_trade"
    assert summary["records"][0]["status"] == "block"


def test_approval_execution_renders_markdown():
    summary = summarize_approval_execution(
        [
            {
                "created_at": "2026-05-30T09:30:00+00:00",
                "symbol": "000001",
                "status": "pass",
                "confirmed_value": 10000,
                "suggested_quantity": 1000,
            }
        ],
        [
            {
                "date": "2026-05-30",
                "symbol": "000001",
                "side": "BUY",
                "price": 10,
                "quantity": 1000,
                "amount": 10000,
                "order_approval_created_at": "2026-05-30T09:30:00+00:00",
                "review": "followed approval",
            }
        ],
    )

    content = render_approval_execution_markdown(summary)

    assert "# Approval Execution Audit" in content
    assert "Matched trades: 1" in content
