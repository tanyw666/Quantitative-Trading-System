import pandas as pd

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
