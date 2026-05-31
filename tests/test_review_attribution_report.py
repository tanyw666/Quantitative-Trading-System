from quant_system.reports.review_attribution import build_review_attribution_report, render_review_attribution_markdown


def test_build_review_attribution_report_rolls_up_multiple_root_causes():
    report = build_review_attribution_report(
        trade_plan_audit={
            "total_plans": 2,
            "match_rate": 0.5,
            "unmatched_plans": 1,
            "orphan_trades": 0,
            "avg_price_deviation_pct": 0.04,
        },
        execution_audit={
            "block_count": 1,
            "warn_count": 0,
            "missing_trade_writeback_count": 1,
            "missing_confirmation_trade_count": 1,
        },
        approval_audit={
            "block_count": 1,
            "warn_count": 1,
            "missing_approval_trade_count": 1,
            "fallback_link_count": 1,
        },
        approval_cooldown={"status": "block"},
        gate_review={"violation_count": 1, "buy_status_counts": {"block": 1}, "missing_gate_count": 1},
        trade_stats={"mistake_counts": {"chase": 2}, "discipline_exception_count": 1},
        lifecycle_snapshot={"status": "warn"},
        limit=12,
    )

    areas = report["by_area"]
    signals = {item["signal"] for item in report["root_causes"]}

    assert report["status"] == "block"
    assert report["root_cause_count"] >= 5
    assert areas["planning"] >= 1
    assert areas["execution"] >= 1
    assert areas["approval"] >= 1
    assert areas["gate"] >= 1
    assert areas["behavior"] >= 1
    assert areas["lifecycle"] >= 1
    assert "trade_plan_mismatch" in signals
    assert "execution_block" in signals
    assert "approval_cooldown_block" in signals
    assert report["action_items"][0].startswith("明天先进入“禁止新增 BUY”模式")


def test_render_review_attribution_markdown_outputs_sections():
    content = render_review_attribution_markdown(
        {
            "status": "warn",
            "score": 82,
            "root_cause_count": 2,
            "by_area": {"planning": 1, "approval": 1},
            "root_causes": [
                {
                    "severity": "warn",
                    "area": "planning",
                    "signal": "trade_plan_drift",
                    "evidence": "match_rate=50.0%",
                    "next_action": "Review skipped plans.",
                }
            ],
            "action_items": ["Review skipped plans."],
        }
    )

    assert "# 复盘归因" in content
    assert "## 根因明细" in content
    assert "## 行动项" in content
