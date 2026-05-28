from quant_system.reports.experiment_summary import render_experiment_summary_lines


def test_render_experiment_summary_lines_includes_full_recommendation():
    lines = render_experiment_summary_lines(
        {
            "preferred_horizon": 3,
            "min_count": 5,
            "result_count": 2,
            "recommendation": {
                "name": "balanced",
                "strategy": "strong_stock_screen",
                "params": {"min_20d_return": 0.12},
                "mean_return": 0.03,
                "win_rate": 0.6,
                "count": 5,
                "score": 0.0315,
                "reason": "样本达标",
            },
        }
    )

    content = "\n".join(lines)

    assert "推荐参数组：balanced" in content
    assert "参数：min_20d_return=0.12" in content
    assert "平均收益：3.00%" in content
    assert "推荐原因：样本达标" in content


def test_render_experiment_summary_lines_handles_missing_summary():
    assert render_experiment_summary_lines(None) == ["- 暂无策略实验摘要。"]
