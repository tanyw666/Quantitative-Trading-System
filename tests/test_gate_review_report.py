from quant_system.reports.gate_review import render_gate_review_lines, render_gate_review_markdown


def test_render_gate_review_lines_highlights_gate_discipline():
    lines = render_gate_review_lines(
        {
            "total_trades": 3,
            "gate_record_count": 2,
            "missing_gate_count": 1,
            "status_counts": {"pass": 1, "block": 1},
            "buy_status_counts": {"pass": 1, "block": 1},
            "violation_count": 1,
            "violation_rate": 0.5,
            "by_reason": {"data_health_failed": 1},
            "by_strategy": {"strong_stock_screen": 2},
            "by_symbol": {"000002": 1},
            "action_items": ["Review every BUY executed under warn/block status and mark whether it was a planned exception."],
        }
    )
    content = "\n".join(lines)

    assert "Gate records" in content
    assert "Missing gate snapshots" in content
    assert "BUY violation rate" in content
    assert "Top reason" in content
    assert "Action Items" in content


def test_render_gate_review_markdown_renders_recent_records():
    content = render_gate_review_markdown(
        {
            "total_trades": 2,
            "gate_record_count": 2,
            "missing_gate_count": 0,
            "status_counts": {"pass": 1, "warn": 1},
            "buy_status_counts": {"pass": 1, "warn": 1},
            "violation_count": 1,
            "violation_rate": 0.5,
            "by_reason": {"execution_deviation": 1},
            "latest_records": [
                {
                    "date": "2026-05-29",
                    "symbol": "000001",
                    "name": "Demo",
                    "side": "BUY",
                    "strategy": "strong_stock_screen",
                    "status": "warn",
                    "reasons": ["execution_deviation"],
                }
            ],
            "latest_violations": [
                {
                    "date": "2026-05-29",
                    "symbol": "000001",
                    "name": "Demo",
                    "strategy": "strong_stock_screen",
                    "status": "warn",
                    "message": "planned exception",
                }
            ],
            "action_items": ["Review every BUY executed under warn/block status and mark whether it was a planned exception."],
        }
    )

    assert "# Gate Review" in content
    assert "Recent Gate Records" in content
    assert "Warn/Block BUY Records" in content
    assert "000001 Demo" in content
