from datetime import datetime

from quant_system.reports.trading_day_timeline import build_trading_day_timeline, render_trading_day_timeline_markdown


def test_trading_day_timeline_warns_when_candidates_need_confirmations():
    timeline = build_trading_day_timeline(
        now=datetime.fromisoformat("2026-05-30T10:00:00"),
        final_battle_plan={"status": "pass", "buy_candidates": [{"symbol": "000001"}]},
        execution_confirmations=[],
        trade_records=[],
        execution_audit={},
        lifecycle_snapshot={"status": "pass"},
        gate_review={},
    )

    assert timeline["status"] == "warn"
    assert any("执行确认" in item for item in timeline["action_items"])


def test_trading_day_timeline_blocks_on_approval_cooldown():
    timeline = build_trading_day_timeline(
        now=datetime.fromisoformat("2026-05-30T10:00:00"),
        final_battle_plan={"status": "pass", "buy_candidates": [{"symbol": "000001"}]},
        execution_confirmations=[],
        trade_records=[],
        execution_audit={},
        lifecycle_snapshot={"status": "pass"},
        gate_review={},
        approval_cooldown={"status": "block", "constraints": [{"strategy": "dragon"}]},
    )

    assert timeline["status"] == "block"
    assert any(phase["phase"] == "approval_discipline" for phase in timeline["phases"])


def test_trading_day_timeline_blocks_on_execution_audit_block():
    timeline = build_trading_day_timeline(
        now=datetime.fromisoformat("2026-05-30T16:00:00"),
        final_battle_plan={"status": "pass"},
        execution_confirmations=[{"status": "block"}],
        trade_records=[{"side": "BUY"}],
        execution_audit={"block_count": 1},
        lifecycle_snapshot={"status": "pass"},
        gate_review={},
    )

    assert timeline["status"] == "block"


def test_render_trading_day_timeline_markdown_shows_phase_sections():
    timeline = build_trading_day_timeline(
        now=datetime.fromisoformat("2026-05-30T15:30:00"),
        final_battle_plan={"status": "pass"},
        execution_confirmations=[],
        trade_records=[],
        execution_audit={},
        lifecycle_snapshot={"status": "pass"},
        gate_review={},
    )

    content = render_trading_day_timeline_markdown(timeline)

    assert "# 交易日时间线" in content
    assert "盘前准备阶段" in content
    assert "审批纪律阶段" in content
    assert "收盘生命周期阶段" in content
