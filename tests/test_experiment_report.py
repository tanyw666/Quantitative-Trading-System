from quant_system.reports.experiments import ExperimentReport, build_experiment_summary_payload, recommend_experiment


def sample_results():
    return [
        {
            "name": "balanced",
            "strategy": "strong_stock_screen",
            "params": {"min_20d_return": 0.12},
            "scoring_weights": {"momentum_20": 0.5},
            "summary": [{"horizon": 3, "count": 5, "mean_return": 0.03, "win_rate": 0.6}],
        },
        {
            "name": "aggressive",
            "strategy": "strong_stock_screen",
            "params": {"min_20d_return": 0.08},
            "scoring_weights": {"momentum_20": 0.6},
            "summary": [{"horizon": 3, "count": 8, "mean_return": 0.02, "win_rate": 0.7}],
        },
    ]


def test_recommend_experiment_prefers_mean_return_after_sample_gate():
    recommendation = recommend_experiment(sample_results())

    assert recommendation
    assert recommendation.name == "balanced"
    assert recommendation.params == {"min_20d_return": 0.12}
    assert recommendation.strategy == "strong_stock_screen"
    assert recommendation.score > 0


def test_experiment_report_renders_markdown_table():
    content = ExperimentReport().render(sample_results())

    assert "推荐参数组" in content
    assert "min_20d_return=0.12" in content
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


def test_build_experiment_summary_payload_includes_recommendation():
    payload = build_experiment_summary_payload(sample_results())

    assert payload["preferred_horizon"] == 3
    assert payload["min_count"] == 5
    assert payload["result_count"] == 2
    assert payload["recommendation"]["name"] == "balanced"
    assert payload["recommendation"]["params"] == {"min_20d_return": 0.12}


def test_build_experiment_summary_payload_handles_no_recommendation():
    payload = build_experiment_summary_payload(
        [
            {
                "name": "tiny",
                "params": {},
                "summary": [{"horizon": 3, "count": 1, "mean_return": 0.10, "win_rate": 1.0}],
            }
        ]
    )

    assert payload["recommendation"] is None
