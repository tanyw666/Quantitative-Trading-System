from quant_system.reports.constraint_summary import render_constraint_summary_lines


def test_render_constraint_summary_lines_renders_alert_labels_and_recent_records():
    lines = render_constraint_summary_lines(
        {
            "total": 2,
            "warn_count": 1,
            "block_count": 1,
            "by_strategy": {"dragon_leader": 2},
            "by_alert": {"execution_deviation": 1, "mistake_cluster": 1},
            "trend": {
                "as_of": "2026-05-29",
                "windows": {
                    "5": {"total": 2, "warn_count": 1, "block_count": 1, "top_strategy": "dragon_leader"},
                    "10": {"total": 2, "warn_count": 1, "block_count": 1, "top_strategy": "dragon_leader"},
                },
            },
            "latest_created_at": "2026-05-29T09:10:00+00:00",
            "records": [
                {
                    "created_at": "2026-05-29T09:00:00+00:00",
                    "source": "portfolio.allocate",
                    "strategy": "dragon_leader",
                    "alert_level": "warn",
                    "action": "reduce",
                    "alerts": ["execution_deviation"],
                },
                {
                    "created_at": "2026-05-29T09:10:00+00:00",
                    "source": "portfolio.precheck",
                    "strategy": "dragon_leader",
                    "alert_level": "block",
                    "action": "pause",
                    "alerts": ["mistake_cluster"],
                },
            ],
        }
    )
    content = "\n".join(lines)

    assert "触发次数：2" in content
    assert "预警/阻断：1 / 1" in content
    assert "高频策略：dragon_leader" in content
    assert "执行偏差过大" in content
    assert "错误集中" in content
    assert "暂停策略" in content
    assert "近5日趋势" in content


def test_render_constraint_summary_lines_handles_empty_summary():
    assert render_constraint_summary_lines(None) == ["- 暂无策略约束触发记录。"]
