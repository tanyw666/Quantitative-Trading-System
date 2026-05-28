from quant_system.reports.experiments import ExperimentReport, recommend_experiment


def sample_results():
    return [
        {
            "name": "balanced",
            "params": {"min_20d_return": 0.12},
            "summary": [{"horizon": 3, "count": 5, "mean_return": 0.03, "win_rate": 0.6}],
        },
        {
            "name": "aggressive",
            "params": {"min_20d_return": 0.08},
            "summary": [{"horizon": 3, "count": 8, "mean_return": 0.02, "win_rate": 0.7}],
        },
    ]


def test_recommend_experiment_prefers_mean_return_after_sample_gate():
    recommendation = recommend_experiment(sample_results())

    assert recommendation
    assert recommendation.name == "balanced"
    assert recommendation.score > 0


def test_experiment_report_renders_markdown_table():
    content = ExperimentReport().render(sample_results())

    assert "推荐参数组" in content
    assert "| 参数组 |" in content
    assert "balanced" in content
    assert "至少 5 个有效样本" in content


def test_recommend_experiment_requires_minimum_sample_count():
    recommendation = recommend_experiment(
        [
            {
                "name": "lucky",
                "params": {},
                "summary": [{"horizon": 3, "count": 1, "mean_return": 0.20, "win_rate": 1.0}],
            }
        ]
    )

    assert recommendation is None


def test_recommend_experiment_falls_back_to_available_horizon():
    recommendation = recommend_experiment(
        [
            {
                "name": "one_day",
                "params": {},
                "summary": [{"horizon": 1, "count": 6, "mean_return": 0.01, "win_rate": 0.55}],
            }
        ]
    )

    assert recommendation
    assert recommendation.horizon == 1


def test_experiment_report_allows_custom_recommendation_gate():
    content = ExperimentReport(preferred_horizon=1, min_count=1).render(
        [
            {
                "name": "quick_check",
                "params": {},
                "summary": [{"horizon": 1, "count": 1, "mean_return": 0.02, "win_rate": 1.0}],
            }
        ]
    )

    assert "推荐参数组：quick_check" in content
    assert "优先参考 1 日周期，至少 1 个有效样本" in content
