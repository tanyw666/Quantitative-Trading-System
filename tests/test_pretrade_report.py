import pandas as pd

from quant_system.reports.premarket import PremarketReport, PremarketReportInput
from quant_system.reports.pretrade import render_precheck_markdown, render_precheck_summary_lines
from quant_system.risk.pretrade import run_pretrade_check


def candidates():
    return pd.DataFrame(
        {
            "symbol": ["000001"],
            "name": ["Demo"],
            "score": [100],
            "risk_grade": ["medium"],
            "atr_stop_price": [33.8],
        }
    )


def test_render_precheck_markdown_includes_checklist_and_actions():
    result = run_pretrade_check(
        candidates(),
        {"regime": "warm", "stance": "适度进攻"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.10,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    content = render_precheck_markdown(result, {"regime": "warm", "stance": "适度进攻"})

    assert "Pretrade Check 000001" in content
    assert "检查项" in content
    assert "动作清单" in content
    assert "总状态：pass" in content


def test_render_precheck_summary_lines_includes_candidate_status_and_action():
    result = run_pretrade_check(
        candidates(),
        {"regime": "warm", "stance": "适度进攻"},
        symbol="000001",
        entry_price=38,
        planned_pct=0.10,
        cash=100000,
        stop_price=35,
        target_price=44,
    )

    lines = render_precheck_summary_lines([result.to_dict()])
    joined = "\n".join(lines)

    assert "交易前预检预览" not in joined
    assert "通过 1" in joined
    assert "000001 Demo" in joined
    assert "可按计划执行" not in joined


def test_premarket_report_renders_holding_action_plan():
    content = PremarketReport().render(
        PremarketReportInput(
            title="盘前",
            market_temperature={"score": 60, "regime": "warm", "stance": "适度进攻"},
            market_context=None,
            data_health=None,
            candidates=[],
            allocation_plan={"target_exposure_pct": 0.2, "allocated_pct": 0.1, "items": []},
            pretrade_checks=[],
            position_book={"total_market_value": 1000, "total_exposure_pct": 0.1, "total_unrealized_pnl": 50, "positions": []},
            holding_risk={"status": "warn", "checks": []},
            holding_action_plan={
                "status": "warn",
                "exit_count": 1,
                "reduce_count": 0,
                "watch_count": 0,
                "hold_count": 0,
                "actions": [
                    {"symbol": "000001", "action": "exit", "status": "block", "current_quantity": 100, "target_quantity": 0, "reason": "触发止损"},
                ],
                "action_items": ["先处理止损动作"],
            },
            action_execution_summary={
                "actionable_count": 1,
                "executed_count": 1,
                "partial_count": 0,
                "missed_count": 0,
                "execution_rate": 1.0,
                "avg_delay_days": 0.0,
                "avg_price_deviation_pct": -0.01,
                "records": [{"action_date": "2026-05-29", "symbol": "000001", "action": "exit", "execution_status": "executed", "required_quantity": 100, "executed_quantity": 100, "delay_days": 0}],
            },
        )
    )

    assert "持仓动作计划" in content
    assert "持仓动作执行审计" in content
    assert "000001" in content
    assert "触发止损" in content
