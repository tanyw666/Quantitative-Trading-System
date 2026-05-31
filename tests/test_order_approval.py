from pathlib import Path

from quant_system.portfolio.order_approval import (
    append_order_approval_record,
    build_order_approval,
    read_order_approval_records,
    render_order_approval_markdown,
    render_order_approval_summary_markdown,
    summarize_order_approvals,
)


def sample_approval(status: str = "pass") -> dict:
    return build_order_approval(
        symbol="000001",
        assistant={"status": "pass", "urgent_actions": [{"text": "Watch the opening auction."}]},
        battle_plan={"status": "pass", "reasons": []},
        pretrade={"status": "pass", "action_items": ["Keep stop at 9.50."]},
        confirmation={
            "status": status,
            "confirmed_pct": 0.1 if status == "pass" else 0.05,
            "confirmed_value": 10000 if status == "pass" else 5000,
            "suggested_quantity": 1000 if status == "pass" else 500,
            "action_items": ["Re-check price right before order entry."],
        },
        tradability={
            "status": status,
            "checks": [{"name": "price_vs_close", "status": status, "message": "demo"}] if status != "pass" else [],
            "action_items": ["Confirm the symbol is still tradable."],
        },
    )


def test_order_approval_rolls_up_warn_and_renders():
    record = sample_approval("warn")

    assert record["status"] == "warn"
    assert record["suggested_quantity"] == 500
    assert any("tradability.price_vs_close" in reason for reason in record["reasons"])
    content = render_order_approval_markdown(record)
    assert "# Order Approval" in content
    assert "Suggested quantity: 500" in content


def test_order_approval_includes_pretrade_and_confirmation_check_reasons():
    record = build_order_approval(
        symbol="000001",
        pretrade={
            "status": "block",
            "checks": [
                {
                    "name": "false_breakout",
                    "status": "block",
                    "message": "False-breakout flag is active; do not chase this setup.",
                }
            ],
        },
        confirmation={
            "status": "warn",
            "checks": [
                {
                    "name": "price_drift",
                    "status": "warn",
                    "message": "Current price is above reference.",
                }
            ],
        },
    )

    assert record["status"] == "block"
    assert record["suggested_quantity"] == 0
    assert any("pretrade.false_breakout" in reason for reason in record["reasons"])
    assert any("confirmation.price_drift" in reason for reason in record["reasons"])


def test_order_approval_record_round_trip_and_summary(tmp_path: Path):
    log_path = tmp_path / "approvals.jsonl"
    first = sample_approval("pass")
    second = sample_approval("warn")
    second["symbol"] = "000002"
    append_order_approval_record(log_path, first)
    append_order_approval_record(log_path, second)

    records = read_order_approval_records(log_path, limit=1)
    summary = summarize_order_approvals(read_order_approval_records(log_path), limit=5)

    assert len(records) == 1
    assert records[0]["symbol"] == "000002"
    assert summary["warn_count"] == 1
    assert summary["by_symbol"]["000001"] == 1
    assert "# Order Approval History" in render_order_approval_summary_markdown(summary)
