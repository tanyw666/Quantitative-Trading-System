from quant_system.portfolio.trading_day_state import (
    apply_trading_day_template,
    build_trading_day_state,
    summarize_trading_day_state_records,
)


def test_apply_trading_day_template_overrides_phase_content():
    timeline = {
        "generated_at": "2026-05-30T10:00:00",
        "status": "warn",
        "phases": [
            {
                "phase": "intraday",
                "title": "盘中阶段",
                "status": "warn",
                "due": "收盘前",
                "checklist": ["原始任务"],
                "missing": [],
                "next_step": "原始动作",
            }
        ],
        "action_items": ["原始提醒"],
    }

    updated = apply_trading_day_template(
        timeline,
        {
            "intraday": {
                "title": "盘中执行阶段",
                "extra_checklist": ["检查盘口确认"],
                "extra_missing": ["尚未检查盘口确认"],
                "next_step": "先检查盘口确认再继续",
            }
        },
    )

    phase = updated["phases"][0]
    assert phase["title"] == "盘中执行阶段"
    assert "检查盘口确认" in phase["checklist"]
    assert "尚未检查盘口确认" in phase["missing"]
    assert updated["status"] == "warn"


def test_build_and_summarize_trading_day_state_records():
    timeline = {
        "generated_at": "2026-05-30T15:30:00",
        "status": "block",
        "phases": [
            {"phase": "premarket", "title": "盘前", "status": "pass", "due": "开盘前", "checklist": ["生成计划"], "missing": [], "next_step": "继续"},
            {"phase": "post_trade", "title": "回写", "status": "block", "due": "盘后", "checklist": ["回写成交"], "missing": ["缺成交回写"], "next_step": "先补回写"},
        ],
        "action_items": ["缺成交回写"],
    }

    record = build_trading_day_state(timeline, trading_date="2026-05-30", source="workflow.trading-day")
    summary = summarize_trading_day_state_records([record], limit=10)

    assert record["phase_count"] == 2
    assert record["block_count"] == 1
    assert summary["status_counts"]["block"] == 1
    assert summary["phase_problem_counts"]["post_trade"] == 1
    assert any("post_trade" in item or "回写" in item for item in summary["action_items"])
