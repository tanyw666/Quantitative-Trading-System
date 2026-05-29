from __future__ import annotations

from quant_system.optimizer.health_labels import alert_reason_label, alert_reasons_text


def render_strategy_health_lines(strategy_health: list[dict] | None, limit: int = 5) -> list[str]:
    if not strategy_health:
        return ["- 暂无策略健康度数据。"]

    lines = [
        "| 策略 | 评分 | 状态 | 动作 | 告警 | 选股 | 交易 | 晋级 | 偏差 | 错误 |",
        "| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in strategy_health[:limit]:
        deviation = item.get("avg_execution_deviation_pct")
        deviation_text = f"{float(deviation):.2%}" if deviation is not None else "-"
        mistake_text = item.get("top_mistake") or "-"
        alert_text = _alert_label(str(item.get("alert_level", "pass")))
        lines.append(
            f"| {item.get('strategy', '')} | "
            f"{float(item.get('score', 0)):.1f} | "
            f"{_status_label(str(item.get('status', '')))} | "
            f"{_action_label(str(item.get('action', '')))} | "
            f"{alert_text} | "
            f"{int(item.get('selection_count', 0))} | "
            f"{int(item.get('trade_count', 0))} | "
            f"{int(item.get('promotion_count', 0))} | "
            f"{deviation_text} | "
            f"{mistake_text} |"
        )
    leader = strategy_health[0]
    lines.append("")
    lines.append(
        f"- 当前优先跟踪：{leader.get('strategy', '')}，"
        f"评分 {float(leader.get('score', 0)):.1f}，"
        f"建议 {_action_label(str(leader.get('action', '')))}。"
    )
    if leader.get("top_tag"):
        lines.append(f"- 最近交易标签重心：{leader.get('top_tag')}。")
    if leader.get("alerts"):
        lines.append(f"- 当前告警：{alert_reasons_text(leader.get('alerts', []))}。")
    policy = leader.get("constraint_policy") or {}
    if policy.get("note"):
        lines.append(f"- 执行状态：{policy.get('note')}")
    config = leader.get("constraint_policy_config") or {}
    if config:
        lines.append(
            "- 风控模板："
            f"观察窗{int(config.get('window_days', 0))}日，"
            f"{int(config.get('cooldown_block_count', 0))}次阻断进冷静期，"
            f"{int(config.get('warn_escalation_count', 0))}次预警降级，"
            f"恢复需{int(config.get('recover_after_clean_days', 0))}日干净记录。"
        )
    return lines


def _status_label(status: str) -> str:
    return {"strong": "强势", "watch": "观察", "weak": "降权"}.get(status, status)


def _action_label(action: str) -> str:
    return {"increase": "提高优先级", "keep": "保持观察", "reduce": "降低仓位/暂停", "pause": "暂停策略"}.get(action, action)


def _alert_label(level: str) -> str:
    return {"pass": "正常", "warn": "预警", "block": "阻断"}.get(level, level)


def _alert_reason_label(alert: str) -> str:
    return alert_reason_label(alert)
