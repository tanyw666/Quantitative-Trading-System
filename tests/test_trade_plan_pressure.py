from quant_system.reports.trade_plan_pressure import format_trade_plan_pressure, normalize_trade_plan_pressure


def test_normalize_trade_plan_pressure_prefers_audit_payload():
    pressure = normalize_trade_plan_pressure(
        {"trade_plan_audit": {"match_rate": 0.72, "unmatched_plans": 2, "orphan_trades": 1}},
        {"match_rate": 0.9},
    )

    assert pressure["match_rate"] == 0.72
    assert pressure["unmatched_plans"] == 2
    assert pressure["orphan_trades"] == 1


def test_format_trade_plan_pressure_renders_all_key_fields():
    text = format_trade_plan_pressure(
        {
            "match_rate": 0.75,
            "unmatched_plans": 1,
            "orphan_trades": 2,
            "avg_price_deviation_pct": 0.04,
            "score": 82.5,
            "status": "watch",
        }
    )

    assert "命中率 75.0%" in text
    assert "失配 1" in text
    assert "孤儿成交 2" in text
    assert "平均偏差 4.00%" in text
    assert "评分 82.5" in text
    assert "状态 watch" in text
