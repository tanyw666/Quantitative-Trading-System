from quant_system.reports.promotion_summary import render_promotion_summary_lines


def test_render_promotion_summary_lines_includes_best_backtest_and_records():
    lines = render_promotion_summary_lines(
        {
            "total": 1,
            "ok_count": 1,
            "failed_count": 0,
            "backtest_count": 1,
            "latest_created_at": "2026-05-28T08:48:17+00:00",
            "best_backtest": {
                "output": "configs/strategies/promoted.yaml",
                "total_return": 0.05,
                "sharpe": 1.2,
                "trades": 3,
            },
            "records": [
                {
                    "created_at": "2026-05-28T08:48:17+00:00",
                    "output": "configs/strategies/promoted.yaml",
                    "ok": True,
                    "total_return": 0.05,
                    "sharpe": 1.2,
                }
            ],
        }
    )

    content = "\n".join(lines)

    assert "晋升记录：1 条" in content
    assert "最佳回测晋升" in content
    assert "总收益 5.00%" in content
    assert "promoted.yaml" in content


def test_render_promotion_summary_lines_handles_empty_summary():
    assert render_promotion_summary_lines(None) == ["- 暂无策略晋升历史。"]
    assert render_promotion_summary_lines({"total": 0}) == ["- 暂无策略晋升历史。"]


def test_render_promotion_summary_lines_uses_clean_summary_format():
    lines = render_promotion_summary_lines(
        {
            "total": 1,
            "ok_count": 1,
            "failed_count": 0,
            "backtest_count": 1,
            "latest_created_at": "2026-05-28T08:48:17+00:00",
            "trade_plan_pressure": {"score": 87, "status": "watch", "match_rate": 0.62, "unmatched_plans": 3, "orphan_trades": 1},
            "best_backtest": {
                "output": "configs/strategies/promoted.yaml",
                "total_return": 0.05,
                "sharpe": 1.2,
                "trades": 3,
            },
            "records": [
                {
                    "created_at": "2026-05-28T08:48:17+00:00",
                    "output": "configs/strategies/promoted.yaml",
                    "ok": True,
                    "total_return": 0.05,
                    "sharpe": 1.2,
                    "trade_plan_pressure": {"score": 87, "status": "watch"},
                }
            ],
        }
    )

    content = "\n".join(lines)
    assert "晋升记录：1 条" in content
    assert "计划压力" in content
    assert "promoted.yaml" in content
    assert "87.0/watch" in content
