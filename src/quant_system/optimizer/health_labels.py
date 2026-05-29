from __future__ import annotations


ALERT_REASON_LABELS = {
    "execution_deviation": "执行偏差过大",
    "mistake_cluster": "错误集中",
    "behavior_mistake": "行为错误高频",
    "emotion_tag": "情绪化交易",
    "negative_flow": "净流出恶化",
    "low_win_rate": "胜率偏低",
    "constraint_cooldown": "策略冷静期",
    "repeated_warn": "连续预警",
    "recovery_probe": "恢复试仓",
}


def alert_reason_label(alert: str) -> str:
    return ALERT_REASON_LABELS.get(str(alert), str(alert))


def alert_reasons_text(alerts: list[str] | tuple[str, ...] | None) -> str:
    values = [alert_reason_label(item) for item in (alerts or []) if str(item).strip()]
    return "、".join(values) if values else "无"
