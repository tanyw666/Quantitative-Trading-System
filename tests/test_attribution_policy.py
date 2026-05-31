from quant_system.risk.attribution_policy import build_attribution_policy, render_attribution_policy_markdown


def test_build_attribution_policy_turns_block_causes_into_constraints():
    policy = build_attribution_policy(
        {
            "status": "block",
            "score": 50,
            "root_cause_count": 2,
            "by_area": {"execution": 1, "approval": 1},
            "summary": {"gate_violations": 1, "lifecycle_status": "warn"},
            "root_causes": [
                {"severity": "block", "area": "execution", "signal": "missing_execution_confirmation", "evidence": "missing=1"},
                {"severity": "block", "area": "approval", "signal": "approval_cooldown_block", "evidence": "cooldown=block"},
            ],
        },
        default_strategy="dragon",
        effective_date="2026-05-31",
        created_at="2026-05-30T15:30:00+00:00",
    )

    assert policy["status"] == "block"
    assert policy["constraint_count"] == 2
    assert all(item["action"] == "pause" for item in policy["constraints"])
    assert all(item["strategy"] == "dragon" for item in policy["constraints"])
    assert policy["discipline_record"]["status"] == "block"
    assert policy["discipline_record"]["date"] == "2026-05-31"
    assert "no-new-BUY" in policy["discipline_record"]["advice"][0]


def test_render_attribution_policy_markdown_outputs_sections():
    content = render_attribution_policy_markdown(
        {
            "status": "warn",
            "effective_date": "2026-05-31",
            "constraints": [
                {
                    "attribution_area": "planning",
                    "alert_level": "warn",
                    "action": "reduce",
                    "exposure_multiplier": 0.5,
                    "alerts": ["trade_plan_drift"],
                    "note": "Reduce exposure.",
                }
            ],
            "discipline_record": {"advice": ["Use reduced exposure."]},
            "action_items": ["Persist generated constraints."],
        }
    )

    assert "# Attribution Policy" in content
    assert "## Next-Day Constraints" in content
    assert "## Discipline Advice" in content
    assert "planning" in content
