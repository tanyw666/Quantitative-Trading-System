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

    assert "门禁记录" in content
    assert "缺失门禁快照" in content
    assert "买入违规率" in content
    assert "高频原因" in content
    assert "行动项" in content


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

    assert "# 门禁审计" in content
    assert "最近门禁记录" in content
    assert "预警/阻断买入记录" in content
    assert "000001 Demo" in content
