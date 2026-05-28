from quant_system.reports.briefing import BriefingInput, BriefingReport, action_notes, candidate_dragon_note


def test_briefing_report_renders_core_sections():
    content = BriefingReport().render(
        BriefingInput(
            title="简报",
            market_temperature={"score": 70, "regime": "warm", "stance": "适度进攻", "advance_ratio": 0.5, "above_ma20_ratio": 0.6},
            candidates=[{"symbol": "000001", "name": "Demo", "score": 90, "risk_grade": "medium", "close": 10}],
            allocation_plan={"target_exposure_pct": 0.6, "allocated_pct": 0.12, "items": []},
            position_book={"total_market_value": 1000, "total_unrealized_pnl": 100, "total_exposure_pct": 0.1, "positions": []},
            holding_risk={"status": "pass", "checks": []},
            sectors=[{"sector": "银行", "strength_score": 80, "candidate_count": 1, "avg_momentum_20": 0.1}],
            experiment_summary={
                "preferred_horizon": 1,
                "min_count": 5,
                "result_count": 2,
                "recommendation": {
                    "name": "gap_hi_0.03_lo_-0.01",
                    "strategy": "dragon_leader",
                    "params": {"max_next_open_gap": 0.03},
                    "mean_return": 0.02,
                    "win_rate": 0.6,
                    "score": 0.05,
                },
            },
        )
    )

    assert "市场温度" in content
    assert "今日候选" in content
    assert "主线板块" in content
    assert "策略参数参考" in content
    assert "gap_hi_0.03_lo_-0.01" in content
    assert "平均收益：2.00%" in content
    assert "今日动作" in content


def test_briefing_report_renders_empty_experiment_summary():
    content = BriefingReport().render(
        BriefingInput(
            title="简报",
            market_temperature={"score": 50, "regime": "warm", "stance": "观察", "advance_ratio": 0.5, "above_ma20_ratio": 0.5},
            candidates=[],
            allocation_plan={"target_exposure_pct": 0, "allocated_pct": 0, "items": []},
            position_book={"total_market_value": 0, "total_unrealized_pnl": 0, "total_exposure_pct": 0, "positions": []},
            holding_risk={"status": "pass", "checks": []},
            experiment_summary={"preferred_horizon": 3, "min_count": 5, "result_count": 1, "recommendation": None},
        )
    )

    assert "暂无满足门槛的推荐参数组" in content


def test_action_notes_prioritizes_blocking_risk():
    notes = action_notes({"regime": "warm"}, [{"symbol": "000001"}], {"status": "block"})

    assert "暂停新增仓位" in notes[0]


def test_candidate_dragon_note_renders_dragon_context():
    note = candidate_dragon_note(
        {
            "dragon_score": 110,
            "seal_quality_score": 95,
            "dragon_state": "repair",
            "entry_gate": "watch",
            "dragon_tags": "reseal-candidate,failed-limit-repair",
        }
    )

    assert "dragon 110.0" in note
    assert "seal 95.0" in note
    assert "gate watch" in note
    assert "failed-limit-repair" in note
