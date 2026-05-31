from quant_system.portfolio.lifecycle_rules import build_lifecycle_rule_plan
from quant_system.portfolio.positions import build_position_book


def test_lifecycle_rules_allow_add_only_after_position_proves_right():
    book = build_position_book(
        [
            {"date": "2026-05-01", "symbol": "000001", "name": "Leader", "side": "BUY", "price": 10, "quantity": 500},
        ],
        cash=100000,
        prices={"000001": 10.6},
    )

    plan = build_lifecycle_rule_plan(
        book,
        stops={"000001": 9.8},
        max_probe_pct=0.05,
        max_position_pct=0.2,
        add_step_pct=0.05,
        add_profit_trigger_pct=0.03,
    ).to_dict()

    item = plan["items"][0]
    assert plan["status"] == "pass"
    assert item["phase"] == "probe"
    assert item["action"] == "add"
    assert item["add_quantity"] > 0
    assert any("add" in text for text in plan["action_items"])


def test_lifecycle_rules_block_averaging_down_and_reduce_near_stop():
    book = build_position_book(
        [
            {"date": "2026-05-01", "symbol": "000001", "name": "Weak", "side": "BUY", "price": 10, "quantity": 1000},
        ],
        cash=100000,
        prices={"000001": 9.55},
    )

    plan = build_lifecycle_rule_plan(
        book,
        stops={"000001": 9.4},
        reduce_loss_warning_pct=0.03,
    ).to_dict()

    item = plan["items"][0]
    assert plan["status"] == "warn"
    assert item["action"] == "reduce"
    assert item["add_blocked"] is True
    assert item["reduce_quantity"] > 0
    assert "average_down_forbidden" in item["rule_tags"]


def test_lifecycle_rules_turn_frequent_exceptions_into_add_penalty():
    book = build_position_book(
        [
            {"date": "2026-05-01", "symbol": "000001", "name": "Leader", "side": "BUY", "price": 10, "quantity": 500},
        ],
        cash=100000,
        prices={"000001": 10.8},
    )

    plan = build_lifecycle_rule_plan(
        book,
        stops={"000001": 9.8},
        discipline_summary={"discipline_exception_count": 2},
        exception_block_threshold=2,
    ).to_dict()

    item = plan["items"][0]
    assert plan["status"] == "block"
    assert plan["exception_penalty"]["action"] == "pause_add"
    assert item["action"] == "hold"
    assert item["add_blocked"] is True
    assert any("exception" in text for text in plan["action_items"])
