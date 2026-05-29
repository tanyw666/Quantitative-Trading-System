from __future__ import annotations

from typing import Any


def render_precheck_markdown(result: Any, market_temperature: dict | None = None, settings: Any | None = None) -> str:
    data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    candidate = data.get("candidate_snapshot") or {}
    lines = [
        f"# Pretrade Check {data.get('symbol', '')}",
        "",
        f"- 总状态：{data.get('status', '')}",
        f"- 计划仓位：{float(data.get('planned_pct', 0)):.1%}（{float(data.get('planned_value', 0)):.2f}）",
        f"- 系统允许：{float(data.get('allowed_pct', 0)):.1%}（{float(data.get('allowed_value', 0)):.2f}）",
        f"- 买入价：{float(data.get('entry_price', 0)):.2f}",
    ]
    if data.get("stop_price") is not None:
        lines.append(f"- 止损价：{float(data.get('stop_price')):.2f}，最大亏损约 {float(data.get('max_loss_value') or 0):.2f}")
    if data.get("target_price") is not None:
        lines.append(f"- 目标价：{float(data.get('target_price')):.2f}，预期收益约 {float(data.get('expected_reward_value') or 0):.2f}")
    if data.get("reward_risk") is not None:
        lines.append(f"- 盈亏比：{float(data.get('reward_risk')):.2f}")

    if market_temperature:
        lines.extend(
            [
                "",
                "## 市场",
                "",
                f"- 状态：{market_temperature.get('regime', '')}",
                f"- 建议：{market_temperature.get('stance', '')}",
            ]
        )

    if settings is not None:
        policy = getattr(getattr(settings, "risk", None), "constraint_policy", None)
        if policy is not None:
            lines.extend(
                [
                    "",
                    "## 风控模板",
                    "",
                    f"- 观察窗：{policy.window_days}日",
                    f"- 单次阻断暂停阈值：{policy.single_block_pause}",
                    f"- 冷静期阻断阈值：{policy.cooldown_block_count}",
                    f"- 恢复干净记录：{policy.recover_after_clean_days}日",
                ]
            )

    if candidate:
        lines.extend(["", "## 候选快照", ""])
        for key in ["name", "score", "risk_grade", "close", "momentum_20", "volume_ratio_20", "reason", "entry_gate"]:
            if key in candidate:
                lines.append(f"- {key}：{candidate[key]}")

    lines.extend(["", "## 检查项", "", "| 项目 | 状态 | 信息 |", "| --- | --- | --- |"])
    for check in data.get("checks", []) or []:
        lines.append(f"| {check.get('name', '')} | {check.get('status', '')} | {check.get('message', '')} |")

    lines.extend(["", "## 动作清单", ""])
    for item in data.get("action_items", []) or []:
        lines.append(f"- {item}")
    return "\n".join(lines)


def render_precheck_summary_lines(results: list[dict] | None, limit: int = 5) -> list[str]:
    if not results:
        return ["- 暂无交易前预检预览；有候选和仓位计划后会自动生成。"]

    visible = list(results[: max(limit, 1)])
    counts = {"pass": 0, "warn": 0, "block": 0}
    for item in results:
        status = str(item.get("status", "") or "")
        if status in counts:
            counts[status] += 1

    lines = [
        (
            f"- 总览：{len(results)} 只候选，"
            f"通过 {counts['pass']}，预警 {counts['warn']}，阻断 {counts['block']}。"
        ),
        "- 说明：这里使用候选收盘价和系统参考止损做预览；正式下单前仍需用实际买入价、止损价和目标价重跑 `portfolio precheck`。",
    ]
    for item in visible:
        symbol = str(item.get("symbol", "") or "")
        candidate = item.get("candidate_snapshot") or {}
        name = str(candidate.get("name", "") or "")
        label = f"{symbol} {name}".strip()
        status = str(item.get("status", "") or "")
        checks = list(item.get("checks", []) or [])
        focus = [check for check in checks if check.get("status") in {"warn", "block"}]
        focus_text = "；".join(str(check.get("message", "")) for check in focus[:2] if check.get("message"))
        suffix = f" 关注：{focus_text}" if focus_text else ""
        stop = item.get("stop_price")
        stop_text = f"，止损 {float(stop):.2f}" if stop is not None else ""
        reward = item.get("reward_risk")
        reward_text = f"，盈亏比 {float(reward):.2f}" if reward is not None else "，目标价待补"
        lines.append(
            f"- [{_status_label(status)}] {label}："
            f"计划 {float(item.get('planned_pct', 0)):.1%}，"
            f"参考买入 {float(item.get('entry_price', 0)):.2f}"
            f"{stop_text}{reward_text}。{suffix}"
        )
    if len(results) > len(visible):
        lines.append(f"- 另有 {len(results) - len(visible)} 只候选未展开。")
    return lines


def _status_label(status: str) -> str:
    return {"pass": "通过", "warn": "预警", "block": "阻断"}.get(status, status or "未知")
