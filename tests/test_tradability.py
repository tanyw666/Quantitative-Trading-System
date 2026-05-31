import pandas as pd

from quant_system.risk.tradability import build_tradability_check, render_tradability_markdown


def sample_frame():
    return pd.DataFrame(
        {
            "date": ["2026-05-29"],
            "symbol": ["000001"],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [10.0],
            "volume": [100000],
        }
    )


def test_tradability_passes_clean_order():
    result = build_tradability_check(
        sample_frame(),
        symbol="000001",
        current_price=10.2,
        planned_pct=0.1,
        cash=100000,
        pretrade_result={"status": "pass", "allowed_pct": 0.12},
        confirmation={"status": "pass"},
        battle_plan={"status": "pass", "blocked_candidates": []},
        as_of="2026-05-30",
    )

    assert result.status == "pass"
    assert result.suggested_quantity == 900
    assert any(check.name == "limit_state" and check.status == "pass" for check in result.checks)


def test_tradability_blocks_stale_and_limit_up_order():
    result = build_tradability_check(
        sample_frame(),
        symbol="000001",
        current_price=10.99,
        planned_pct=0.1,
        cash=100000,
        pretrade_result={"status": "pass", "allowed_pct": 0.12},
        confirmation={"status": "pass"},
        battle_plan={"status": "pass", "blocked_candidates": []},
        as_of="2026-06-05",
        max_stale_days=1,
    )

    assert result.status == "block"
    assert any(check.name == "data_staleness" and check.status == "block" for check in result.checks)
    assert any(check.name == "limit_state" and check.status == "block" for check in result.checks)


def test_render_tradability_markdown_outputs_checks():
    result = build_tradability_check(
        sample_frame(),
        symbol="000001",
        current_price=10.2,
        planned_pct=0.1,
        cash=100000,
        pretrade_result={"status": "warn", "allowed_pct": 0.12},
        confirmation={"status": "warn"},
        battle_plan={"status": "warn", "blocked_candidates": []},
        as_of="2026-05-30",
    )

    content = render_tradability_markdown(result)

    assert "# Tradability Check" in content
    assert "## Checks" in content
    assert "pretrade" in content


def test_tradability_blocks_zero_volume_bar():
    frame = pd.DataFrame(
        {
            "date": ["2026-05-29"],
            "symbol": ["000001"],
            "open": [10.0],
            "high": [10.2],
            "low": [9.9],
            "close": [10.0],
            "volume": [0],
        }
    )

    result = build_tradability_check(
        frame,
        symbol="000001",
        current_price=10.0,
        planned_pct=0.1,
        cash=100000,
        pretrade_result={"status": "pass", "allowed_pct": 0.12},
        confirmation={"status": "pass"},
        battle_plan={"status": "pass", "blocked_candidates": []},
        as_of="2026-05-30",
    )

    assert result.status == "block"
    assert any(check.name == "bar_sanity" and check.status == "block" for check in result.checks)


def test_tradability_infers_20pct_limit_for_chinext_and_blocks_near_limit_up():
    frame = pd.DataFrame(
        {
            "date": ["2026-05-29"],
            "symbol": ["300001"],
            "open": [10.0],
            "high": [10.8],
            "low": [9.9],
            "close": [10.0],
            "volume": [100000],
        }
    )

    result = build_tradability_check(
        frame,
        symbol="300001",
        current_price=11.98,
        planned_pct=0.1,
        cash=100000,
        pretrade_result={"status": "pass", "allowed_pct": 0.12},
        confirmation={"status": "pass"},
        battle_plan={"status": "pass", "blocked_candidates": []},
        as_of="2026-05-30",
    )

    limit_check = next(check for check in result.checks if check.name == "limit_state")

    assert result.status == "block"
    assert limit_check.status == "block"
    assert "20%" in limit_check.message
