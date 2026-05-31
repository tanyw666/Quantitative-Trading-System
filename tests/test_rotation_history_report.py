import json

from quant_system.reports.rotation_history import (
    read_rotation_snapshots,
    render_rotation_history_card_lines,
    render_rotation_history_lines,
    summarize_rotation_history,
)


def test_summarize_rotation_history_tracks_counts_and_trends():
    summary = summarize_rotation_history(
        [
            {
                "created_at": "2026-05-28T09:00:00+00:00",
                "items": [
                    {"strategy": "dragon", "rotation_score": 70, "priority": "观察", "action": "确认单"},
                    {"strategy": "reversal", "rotation_score": 50, "priority": "轻仓", "action": "小仓"},
                ],
            },
            {
                "created_at": "2026-05-29T09:00:00+00:00",
                "items": [
                    {"strategy": "dragon", "rotation_score": 86, "priority": "主打", "action": "主策略"},
                    {"strategy": "reversal", "rotation_score": 38, "priority": "暂停", "action": "暂停"},
                ],
            },
        ]
    )

    assert summary["snapshot_count"] == 2
    assert summary["strategies"][0]["strategy"] == "dragon"
    assert summary["strategies"][0]["trend"] == "up"
    assert summary["strategies"][0]["main_count"] == 1
    assert summary["strategies"][1]["pause_count"] == 1


def test_read_rotation_snapshots_reads_timestamped_json_files(tmp_path):
    path = tmp_path / "rotation_20260529T090000.json"
    path.write_text(
        json.dumps({"created_at": "2026-05-29T09:00:00+00:00", "items": [{"strategy": "dragon"}]}),
        encoding="utf-8",
    )

    snapshots = read_rotation_snapshots(tmp_path)

    assert len(snapshots) == 1
    assert snapshots[0]["_path"] == str(path)


def test_render_rotation_history_lines_renders_markdown_table():
    lines = render_rotation_history_lines(
        {
            "snapshot_count": 1,
            "first_created_at": "2026-05-29T09:00:00+00:00",
            "latest_created_at": "2026-05-29T09:00:00+00:00",
            "strategies": [
                {
                    "strategy": "dragon",
                    "snapshot_count": 1,
                    "avg_rotation_score": 86,
                    "latest_rotation_score": 86,
                    "trend": "up",
                    "main_count": 1,
                    "pause_count": 0,
                    "latest_action": "主策略",
                }
            ],
        }
    )
    content = "\n".join(lines)

    assert "快照数量：1" in content
    assert "走强" in content
    assert "| 策略 | 样本 |" in content


def test_render_rotation_history_card_lines_highlights_trends():
    lines = render_rotation_history_card_lines(
        {
            "snapshot_count": 2,
            "first_created_at": "2026-05-28T09:00:00+00:00",
            "latest_created_at": "2026-05-29T09:00:00+00:00",
            "strategies": [
                {"strategy": "dragon", "latest_rotation_score": 86, "trend": "up", "main_count": 2, "pause_count": 0},
                {"strategy": "reversal", "latest_rotation_score": 40, "trend": "down", "main_count": 0, "pause_count": 2},
            ],
        }
    )

    content = "\n".join(lines)
    assert "走强策略" in content
    assert "走弱策略" in content
    assert "历史综合领先" in content


def test_summarize_rotation_history_tracks_trade_plan_match_rate():
    summary = summarize_rotation_history(
        [
            {
                "created_at": "2026-05-29T09:00:00+00:00",
                "items": [
                    {"strategy": "dragon", "rotation_score": 82, "priority": "主打", "action": "作为下个交易日主策略", "trade_plan_match_rate": 0.5},
                    {"strategy": "dragon", "rotation_score": 78, "priority": "观察", "action": "只做计划内确认单", "trade_plan_match_rate": 0.75},
                ],
            }
        ]
    )

    strategy = summary["strategies"][0]
    assert strategy["avg_trade_plan_match_rate"] == 0.625
    assert strategy["main_count"] == 1
    assert strategy["pause_count"] == 0
    assert strategy["low_trade_plan_match_count"] == 2


def test_summarize_rotation_history_tracks_lifecycle_memory_pressure():
    summary = summarize_rotation_history(
        [
            {
                "created_at": "2026-05-29T09:00:00+00:00",
                "items": [
                    {
                        "strategy": "dragon",
                        "rotation_score": 82,
                        "priority": "主打",
                        "action": "作为下个交易日主策略",
                        "lifecycle_pressure": {"score": 62, "alert_level": "block", "doctor_status": "warn"},
                    },
                    {
                        "strategy": "dragon",
                        "rotation_score": 75,
                        "priority": "观察",
                        "action": "只做计划内确认单",
                        "lifecycle_pressure": {"score": 78, "alert_level": "warn", "doctor_status": "pass"},
                    },
                ],
            }
        ]
    )

    strategy = summary["strategies"][0]
    assert strategy["avg_lifecycle_score"] == 70.0
    assert strategy["lifecycle_block_count"] == 1
    assert strategy["doctor_warn_count"] == 1


def test_render_rotation_history_card_lines_mentions_low_trade_plan_match():
    lines = render_rotation_history_card_lines(
        {
            "snapshot_count": 1,
            "first_created_at": "2026-05-29T09:00:00+00:00",
            "latest_created_at": "2026-05-29T09:00:00+00:00",
            "strategies": [
                {
                    "strategy": "dragon",
                    "latest_rotation_score": 80,
                    "trend": "flat",
                    "main_count": 1,
                    "pause_count": 0,
                    "low_trade_plan_match_count": 2,
                }
            ],
        }
    )

    assert "计划失配偏多" in "\n".join(lines)


def test_render_rotation_history_card_lines_mentions_lifecycle_pressure_hotspots():
    lines = render_rotation_history_card_lines(
        {
            "snapshot_count": 1,
            "first_created_at": "2026-05-29T09:00:00+00:00",
            "latest_created_at": "2026-05-29T09:00:00+00:00",
            "strategies": [
                {
                    "strategy": "dragon",
                    "latest_rotation_score": 80,
                    "trend": "flat",
                    "main_count": 1,
                    "pause_count": 0,
                    "lifecycle_block_count": 2,
                }
            ],
        }
    )

    assert "Lifecycle pressure hotspots" in "\n".join(lines)


def test_render_rotation_history_lines_mentions_trade_plan_pressure():
    lines = render_rotation_history_lines(
        {
            "snapshot_count": 1,
            "first_created_at": "2026-05-29T09:00:00+00:00",
            "latest_created_at": "2026-05-29T09:00:00+00:00",
            "strategies": [
                {
                    "strategy": "dragon",
                    "snapshot_count": 1,
                    "avg_rotation_score": 86,
                    "latest_rotation_score": 86,
                    "trend": "up",
                    "main_count": 1,
                    "pause_count": 0,
                    "latest_action": "主策略",
                    "trade_plan_audit": {"match_rate": 0.72, "unmatched_plans": 2, "orphan_trades": 1, "score": 81},
                }
            ],
        }
    )

    content = "\n".join(lines)
    assert "命中率 72.0%" in content
