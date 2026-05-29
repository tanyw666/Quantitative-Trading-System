from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def read_rotation_snapshots(snapshot_dir: Path, limit: int = 20) -> list[dict[str, Any]]:
    if not snapshot_dir.exists():
        return []
    files = sorted(snapshot_dir.glob("rotation_*.json"))
    if limit > 0:
        files = files[-limit:]
    snapshots: list[dict[str, Any]] = []
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload["_path"] = str(path)
            snapshots.append(payload)
    return snapshots


def summarize_rotation_history(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        created_at = snapshot.get("created_at")
        for item in snapshot.get("items", []) or []:
            strategy = str(item.get("strategy", "") or "")
            if not strategy:
                continue
            row = dict(item)
            row["created_at"] = created_at
            by_strategy[strategy].append(row)

    strategies = []
    for strategy, rows in by_strategy.items():
        scores = [float(row.get("rotation_score", 0) or 0) for row in rows]
        priorities = [str(row.get("priority", "") or "") for row in rows]
        strategies.append(
            {
                "strategy": strategy,
                "snapshot_count": len(rows),
                "avg_rotation_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
                "latest_rotation_score": scores[-1] if scores else 0.0,
                "trend": _trend(scores),
                "main_count": priorities.count("主打"),
                "watch_count": priorities.count("观察"),
                "light_count": priorities.count("轻仓"),
                "pause_count": priorities.count("暂停"),
                "latest_action": rows[-1].get("action", "") if rows else "",
            }
        )

    return {
        "snapshot_count": len(snapshots),
        "first_created_at": snapshots[0].get("created_at") if snapshots else None,
        "latest_created_at": snapshots[-1].get("created_at") if snapshots else None,
        "strategies": sorted(
            strategies,
            key=lambda item: (
                -float(item.get("avg_rotation_score", 0) or 0),
                -int(item.get("main_count", 0) or 0),
                str(item.get("strategy", "")),
            ),
        ),
    }


def render_rotation_history_lines(summary: dict[str, Any] | None) -> list[str]:
    if not summary or int(summary.get("snapshot_count", 0) or 0) == 0:
        return ["- 暂无策略轮换快照。"]

    lines = [
        f"- 快照数量：{int(summary.get('snapshot_count', 0))}",
        f"- 覆盖区间：{summary.get('first_created_at', '')} 至 {summary.get('latest_created_at', '')}",
        "",
        "| 策略 | 样本 | 平均轮换分 | 最新分 | 趋势 | 主打 | 暂停 | 最新动作 |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |",
    ]
    for item in summary.get("strategies", []) or []:
        lines.append(
            f"| {item.get('strategy', '')} | "
            f"{int(item.get('snapshot_count', 0))} | "
            f"{float(item.get('avg_rotation_score', 0)):.1f} | "
            f"{float(item.get('latest_rotation_score', 0)):.1f} | "
            f"{_trend_label(str(item.get('trend', '')))} | "
            f"{int(item.get('main_count', 0))} | "
            f"{int(item.get('pause_count', 0))} | "
            f"{item.get('latest_action', '')} |"
        )
    return lines


def render_rotation_history_card_lines(summary: dict[str, Any] | None, limit: int = 3) -> list[str]:
    if not summary or int(summary.get("snapshot_count", 0) or 0) == 0:
        return ["- 暂无策略轮换历史快照。"]

    strategies = list(summary.get("strategies", []) or [])
    improving = [item for item in strategies if item.get("trend") == "up"][:limit]
    weakening = [item for item in strategies if item.get("trend") == "down"][:limit]
    main = sorted(strategies, key=lambda item: (-int(item.get("main_count", 0) or 0), str(item.get("strategy", ""))))[:limit]
    paused = sorted(strategies, key=lambda item: (-int(item.get("pause_count", 0) or 0), str(item.get("strategy", ""))))[:limit]

    lines = [
        f"- 快照数量：{int(summary.get('snapshot_count', 0))}",
        f"- 覆盖区间：{summary.get('first_created_at', '')} 至 {summary.get('latest_created_at', '')}",
        f"- 走强策略：{_strategy_list(improving)}",
        f"- 走弱策略：{_strategy_list(weakening)}",
        f"- 主打次数靠前：{_strategy_list(main, count_key='main_count')}",
        f"- 暂停次数靠前：{_strategy_list(paused, count_key='pause_count')}",
    ]
    if strategies:
        leader = strategies[0]
        lines.append(
            f"- 历史综合领先：{leader.get('strategy', '')}，"
            f"平均轮换分 {float(leader.get('avg_rotation_score', 0)):.1f}，"
            f"趋势 {_trend_label(str(leader.get('trend', '')))}。"
        )
    return lines


def _trend(scores: list[float]) -> str:
    if len(scores) < 2:
        return "flat"
    delta = scores[-1] - scores[0]
    if delta >= 5:
        return "up"
    if delta <= -5:
        return "down"
    return "flat"


def _trend_label(trend: str) -> str:
    return {"up": "走强", "down": "走弱", "flat": "持平"}.get(trend, trend)


def _strategy_list(items: list[dict[str, Any]], count_key: str | None = None) -> str:
    if not items:
        return "无"
    values = []
    for item in items:
        strategy = str(item.get("strategy", "") or "")
        if count_key:
            values.append(f"{strategy}({int(item.get(count_key, 0) or 0)})")
        else:
            values.append(f"{strategy}({float(item.get('latest_rotation_score', 0) or 0):.1f})")
    return "、".join(values)
